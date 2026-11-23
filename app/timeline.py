from __future__ import annotations

import json
import logging
import math
import re
import shutil
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, Field

from app.media import validate_mp4

LOGGER = logging.getLogger(__name__)
MAX_EVENTS = 10000


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
            if path.exists() and path.stat().st_size > 8 * 1024**2:
                rows = self._read(path)
                pending = path.with_suffix(f".{uuid4().hex}.part")
                try:
                    pending.write_text("\n".join(json.dumps(item) for item in rows) + "\n", encoding="utf-8")
                    pending.replace(path)
                finally:
                    pending.unlink(missing_ok=True)
            with path.open("ab") as handle:
                handle.write((json.dumps(row) + "\n").encode("utf-8"))
        return row

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
    def __init__(self, timeline, moonraker, cameras):
        self.timeline = timeline
        self.moonraker = moonraker
        self.cameras = cameras
        self.previous = {}
        self.stop = Event()
        self.worker = Thread(target=self._run, name="klipper-timeline", daemon=True)

    def _run(self):
        while not self.stop.is_set():
            self.poll()
            self.stop.wait(2)

    def poll(self):
        printers = {}
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


def extract_segment(source: Path, output: Path, start: float, end: float, reserve: int) -> None:
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
        "-movflags", "+faststart", "-n", str(output),
    ]
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
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
