from __future__ import annotations

import json
import hashlib
import logging
import math
import re
import shutil
import subprocess
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, Field

from app.media import validate_mp4

LOGGER = logging.getLogger(__name__)
MAX_EVENTS = 10000
MAX_LOG_BYTES = 8 * 1024**2
MAX_IMPORT_BYTES = 2 * 1024**2
START_LINE = re.compile(r"^Start printer at .* \(([\d.]+) ([\d.]+)\)$")
STATS_LINE = re.compile(r"^Stats ([\d.]+):")


def klipper_log_events(log: str):
    """Only retain recognized messages, not raw logs or printer configuration."""
    epoch = mono = sample = None
    last_sample = -math.inf
    for line in log.splitlines():
        line = line.removeprefix("INFO:root:").strip()
        start = START_LINE.fullmatch(line)
        stats = STATS_LINE.match(line)
        if start:
            try:
                epoch, mono = map(float, start.groups())
                datetime.fromtimestamp(epoch, timezone.utc)
                if not math.isfinite(mono):
                    raise ValueError
            except (OverflowError, OSError, ValueError):
                epoch = mono = sample = None
                continue
            sample = mono
            last_sample = -math.inf
            kind, message = "klipper.start", "Klipper session started"
        elif line == "Starting Klippy..." or line == "Restarting printer":
            epoch = mono = sample = None
            continue
        elif stats and epoch is not None:
            try:
                sample = float(stats[1])
            except ValueError:
                continue
            if not math.isfinite(sample) or sample < mono:
                sample = None
                continue
            if sample - last_sample < 30:
                continue
            last_sample = sample
            kind, message = "klipper.stats", "Klipper timing sample"
        elif sample is not None and line.startswith(("Transition to shutdown state:", "MCU '", "Internal error during")):
            if line.startswith("MCU '") and "shutdown:" not in line.lower():
                continue
            kind, message = "klipper.shutdown", "Klipper shutdown (aligned to preceding timing sample)"
        else:
            continue
        try:
            source = datetime.fromtimestamp(epoch + (sample - mono), timezone.utc)
        except (OverflowError, OSError, ValueError):
            continue
        event = EventInput(kind=kind, message=message, source_at=source, klipper_eventtime=sample)
        event_id = hashlib.sha256(f"{epoch}:{mono}:{sample}:{kind}".encode()).hexdigest()
        yield event_id, event


class EventInput(BaseModel):
    kind: str = Field(min_length=1, max_length=48, pattern=r"^[a-zA-Z0-9_.-]+$")
    message: str = Field(max_length=500)
    source_at: AwareDatetime | None = None
    klipper_eventtime: float | None = Field(default=None, ge=0, allow_inf_nan=False)


def video_offset(event_at: datetime, frame_zero_at: datetime, correction: float, duration: float) -> float | None:
    offset = (event_at - frame_zero_at).total_seconds() + correction
    return offset if 0 <= offset < duration else None


class Timeline:
    def __init__(self, recordings_root: str):
        self.root = Path(recordings_root).resolve() / ".timeline"
        self.lock = Lock()

    def _path(self, printer_id: str) -> Path:
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", printer_id) or printer_id in {".", ".."}:
            raise ValueError("Invalid printer identifier")
        path = self.root / f"{printer_id}.jsonl"
        if path.resolve() != path:
            raise ValueError("Invalid timeline storage location")
        return path

    def append(self, printer_id: str, event: EventInput, origin: str) -> dict:
        row = event.model_dump(mode="json")
        row.update(id=uuid4().hex, origin=origin, received_at=datetime.now(timezone.utc).isoformat())
        with self.lock:
            path = self._path(printer_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size >= MAX_LOG_BYTES:
                rows = self._read(path)
                retained = deque()
                retained_bytes = 0
                for item in reversed(rows):
                    line = (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8")
                    if retained_bytes + len(line) > MAX_LOG_BYTES // 2:
                        break
                    retained.appendleft(line)
                    retained_bytes += len(line)
                pending = path.with_suffix(f".{uuid4().hex}.part")
                try:
                    pending.write_bytes(b"".join(retained))
                    pending.replace(path)
                finally:
                    pending.unlink(missing_ok=True)
            with path.open("ab") as handle:
                handle.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
        return row

    def import_klipper(self, printer_id: str, log: str) -> dict:
        with self.lock:
            path = self._path(printer_id)
            rows = self._read(path)
            seen = {row.get("id") for row in rows}
            imported = duplicates = 0
            received_at = datetime.now(timezone.utc).isoformat()
            for event_id, event in klipper_log_events(log):
                if event_id in seen:
                    duplicates += 1
                    continue
                seen.add(event_id)
                row = event.model_dump(mode="json")
                row.update(id=event_id, origin="klipper-log", received_at=received_at)
                rows.append(row)
                imported += 1
            if imported:
                path.parent.mkdir(parents=True, exist_ok=True)
                pending = path.with_suffix(f".{uuid4().hex}.part")
                try:
                    encoded = deque()
                    size = 0
                    for row in reversed(rows):
                        line = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
                        if size + len(line) > MAX_LOG_BYTES:
                            break
                        encoded.appendleft(line)
                        size += len(line)
                    pending.write_bytes(b"".join(encoded))
                    pending.replace(path)
                finally:
                    pending.unlink(missing_ok=True)
            return {"imported": imported, "duplicates": duplicates}

    @staticmethod
    def _read(path: Path) -> deque:
        rows = deque(maxlen=MAX_EVENTS)
        if path.exists():
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                        if isinstance(row, dict) and "received_at" in row:
                            rows.append(row)
                    except ValueError:
                        continue
        return rows

    def events(self, printer_id: str) -> list[dict]:
        with self.lock:
            return list(self._read(self._path(printer_id)))


class TimelineMonitor:
    def __init__(self, timeline, moonraker, cameras, printer_configs=tuple):
        self.timeline = timeline
        self.moonraker = moonraker
        self.cameras = cameras
        self.printer_configs = printer_configs
        self.previous = {}
        self.stop = Event()
        self.worker = Thread(target=self._run, name="klipper-timeline", daemon=True)

    def _run(self):
        while not self.stop.is_set():
            self.poll()
            self.stop.wait(2)

    def poll(self):
        printers = {printer.id: printer.moonraker_url for printer in self.printer_configs()
                    if printer.enabled and printer.moonraker_url}
        for camera in self.cameras():
            if camera.enabled and camera.moonraker_url:
                printers.setdefault(camera.printer_id, camera.moonraker_url)
        for printer_id, url in printers.items():
            if self.stop.is_set():
                return
            try:
                status = self.moonraker.fetch_status(url)
                previous = self.previous.get(printer_id)
                current = (status.connection_state, status.printer_status_text,
                           status.current_file_name, status.current_layer)
                eventtime = status.klipper_eventtime
                if previous is None or previous[:3] != current[:3]:
                    message = status.printer_status_text
                    if status.current_file_name:
                        message += f" | {status.current_file_name}"
                    self.timeline.append(printer_id, EventInput(
                        kind="printer.status", message=message[:500], klipper_eventtime=eventtime,
                    ), "moonraker-poll")
                if current[3] is not None and status.monitor_state == "printing" and (
                    previous is None or previous[2:] != current[2:]
                ):
                    self.timeline.append(printer_id, EventInput(
                        kind="print.layer", message=f"Reported layer {current[3]}", klipper_eventtime=eventtime,
                    ), "moonraker-poll")
                self.previous[printer_id] = current
            except (ValueError, OSError):
                LOGGER.warning("Timeline observation failed for printer %s", printer_id)

    def shutdown(self):
        self.stop.set()
        self.worker.join(timeout=4)


def export_captions(path: Path, events: list[dict], zero: datetime, start: float, end: float, clock: str):
    def srt_time(seconds):
        ms = round(seconds * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    def timestamp(value):
        return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat(timespec="milliseconds") if value else "Unavailable"

    markers = []
    for event in events:
        stamp = (event.get("source_at") if clock == "source" else None) or event["received_at"]
        offset = (datetime.fromisoformat(stamp) - zero).total_seconds() - start
        if -5 < offset < end - start:
            markers.append((offset, event))
    markers.sort(key=lambda pair: pair[0])
    duration = end - start
    boundaries = sorted({0.0, duration, *range(1, math.ceil(duration)),
                         *(offset for offset, _ in markers if offset > 0),
                         *(offset + 5 for offset, _ in markers if 0 < offset + 5 < duration)})
    cue = 0
    index = -1
    with path.open("w", encoding="utf-8") as out:
        for left, right in zip(boundaries, boundaries[1:]):
            if srt_time(left) == srt_time(right):
                continue
            cue += 1
            while index + 1 < len(markers) and markers[index + 1][0] <= left:
                index += 1
            event = markers[index][1] if index >= 0 and left < markers[index][0] + 5 else None
            wall = (zero + timedelta(seconds=start + left)).isoformat(timespec="milliseconds")
            out.write(f"{cue}\n{srt_time(left)} --> {srt_time(right)}\nVideo UTC: {wall}\n")
            if event:
                out.write(f"Source: {timestamp(event.get('source_at'))}\nReceived: {timestamp(event['received_at'])}\n")
            out.write("\n")


def extract_segment(source: Path, output: Path, start: float, end: float, reserve: int,
                    *, burn_timestamps: bool = False) -> None:
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end and end - start <= 120):
        raise ValueError("Choose a positive range of up to 120 seconds")
    metadata = validate_mp4(source)
    if end > float(metadata["format"]["duration"]) + 0.001:
        raise ValueError("The selection extends past the end of the recording")
    if shutil.disk_usage(output.parent).free < reserve + 128 * 1024**2:
        raise ValueError("Insufficient space to extract the selected clip")
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-ss", f"{start:.6f}", "-i", str(source),
        "-t", f"{end - start:.6f}", "-map", "0:v:0", "-an", "-c:v", "libx264",
        "-threads", "2", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        *(["-vf", "subtitles=timestamps.srt"] if burn_timestamps else []),
        "-movflags", "+faststart", "-n", str(output),
    ]
    with subprocess.Popen(command, cwd=output.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
        deadline = time.monotonic() + 90
        while process.poll() is None:
            if shutil.disk_usage(output.parent).free < reserve or time.monotonic() > deadline:
                process.kill()
                raise ValueError("Clip extraction exceeded the disk or time limit")
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise ValueError("FFmpeg could not extract the selected clip")
    validate_mp4(output)
