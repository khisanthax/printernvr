from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from subprocess import list2cmdline
from threading import Event, Lock, Thread
from typing import Callable
from urllib.parse import quote

from app.models import ResolvedCamera, TimelapseSessionState
from app.services.moonraker_service import MoonrakerService

LOGGER = logging.getLogger(__name__)

SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
ACTIVE_STATUSES = {"starting", "running", "stopping", "rendering"}
PRINTING_STATES = {"printing"}
TERMINAL_STATES = {"complete", "cancelled", "canceled", "error", "standby", "ready", "idle"}


@dataclass
class ManagedTimelapse:
    printer_id: str
    printer_name: str
    camera_id: str
    camera_name: str
    record_url: str
    moonraker_url: str | None
    interval_seconds: int
    session_id: str
    session_root: Path
    frames_dir: Path
    output_path: Path
    stop_event: Event = field(default_factory=Event)
    state: TimelapseSessionState | None = None
    thread: Thread | None = None
    consecutive_capture_errors: int = 0


class TimelapseManager:
    def __init__(
        self,
        recordings_root: str,
        moonraker_service: MoonrakerService,
        on_timelapse_finished: Callable[[], None] | None = None,
    ) -> None:
        self._recordings_root = Path(recordings_root)
        self._moonraker_service = moonraker_service
        self._on_timelapse_finished = on_timelapse_finished
        self._lock = Lock()
        self._sessions: dict[str, ManagedTimelapse] = {}
        self._states: dict[str, TimelapseSessionState] = {}
        self._load_existing_outputs()

    def start_session(
        self,
        printer_id: str,
        printer_name: str,
        camera: ResolvedCamera,
        interval_seconds: int,
        moonraker_url: str | None = None,
    ) -> TimelapseSessionState:
        if interval_seconds < 1 or interval_seconds > 300:
            raise ValueError("interval_seconds must be between 1 and 300")
        if not camera.enabled:
            raise ValueError(f"Camera '{camera.id}' is disabled")
        if camera.backend_type != "ffmpeg" or not camera.record_url:
            raise ValueError(f"Camera '{camera.id}' does not have a usable RTSP/recording URL")

        safe_printer_id = _safe_path_part(printer_id, "printer id")
        started_at = datetime.utcnow()
        session_id = _unique_session_id(safe_printer_id, started_at)
        session_root = self._recordings_root / "timelapses" / safe_printer_id / session_id
        frames_dir = session_root / "frames"
        output_path = session_root / f"{session_id}.mp4"

        with self._lock:
            existing = self._sessions.get(printer_id)
            if existing and existing.state and existing.state.status in ACTIVE_STATUSES:
                raise ValueError(f"Printer '{printer_id}' already has an active timelapse")
            if output_path.exists():
                raise ValueError(f"Timelapse output already exists for session '{session_id}'")

            frames_dir.mkdir(parents=True, exist_ok=False)

            state = TimelapseSessionState(
                printer_id=printer_id,
                printer_name=printer_name,
                camera_id=camera.id,
                camera_name=camera.name,
                status="starting",
                interval_seconds=interval_seconds,
                frame_count=0,
                started_at=started_at,
                session_id=session_id,
                frames_dir=str(frames_dir),
                output_file=output_path.name,
                output_path=str(output_path),
                output_url=None,
                render_status="idle",
                moonraker_auto_stop_enabled=bool(moonraker_url),
                moonraker_message="Waiting for Moonraker print state" if moonraker_url else "No Moonraker URL configured; manual stop required",
            )
            managed = ManagedTimelapse(
                printer_id=printer_id,
                printer_name=printer_name,
                camera_id=camera.id,
                camera_name=camera.name,
                record_url=camera.record_url,
                moonraker_url=moonraker_url,
                interval_seconds=interval_seconds,
                session_id=session_id,
                session_root=session_root,
                frames_dir=frames_dir,
                output_path=output_path,
                state=state,
            )
            thread = Thread(
                target=self._run_session,
                args=(managed,),
                daemon=True,
                name=f"timelapse-{printer_id}",
            )
            managed.thread = thread
            self._sessions[printer_id] = managed
            self._states[printer_id] = state

        LOGGER.info(
            "Starting timelapse for printer=%s camera=%s interval=%ss session=%s",
            printer_id,
            camera.id,
            interval_seconds,
            session_id,
        )
        thread.start()
        return self.get_state(printer_id)

    def stop_session(self, printer_id: str, reason: str = "manual") -> TimelapseSessionState:
        with self._lock:
            managed = self._sessions.get(printer_id)
            if not managed or not managed.state or managed.state.status not in ACTIVE_STATUSES:
                return self._states.get(printer_id) or TimelapseSessionState(
                    printer_id=printer_id,
                    status="idle",
                    stop_reason="no_active_session",
                )
            managed.state.status = "stopping"
            managed.state.stop_reason = reason
            managed.stop_event.set()
            self._states[printer_id] = managed.state

        LOGGER.info("Stopping timelapse for printer=%s reason=%s", printer_id, reason)
        return self.get_state(printer_id)

    def get_state(self, printer_id: str) -> TimelapseSessionState:
        with self._lock:
            state = self._states.get(printer_id)
            if state:
                return state.model_copy(deep=True)
        return TimelapseSessionState(printer_id=printer_id, status="idle")

    def as_payload(self) -> dict[str, dict]:
        with self._lock:
            return {
                printer_id: state.model_dump(mode="json")
                for printer_id, state in sorted(self._states.items())
            }

    def is_printer_busy(self, printer_id: str) -> bool:
        with self._lock:
            state = self._states.get(printer_id)
            return bool(state and state.status in ACTIVE_STATUSES)

    def is_camera_busy(self, camera_id: str) -> bool:
        with self._lock:
            return any(
                state.camera_id == camera_id and state.status in ACTIVE_STATUSES
                for state in self._states.values()
            )

    def active_paths(self) -> set[str]:
        paths: set[str] = set()
        with self._lock:
            sessions = list(self._sessions.values())

        for session in sessions:
            state = session.state
            if not state or state.status not in ACTIVE_STATUSES:
                continue
            if session.output_path.exists():
                paths.add(str(session.output_path.resolve(strict=False)))
            if session.frames_dir.exists():
                for frame in session.frames_dir.glob("frame_*.jpg"):
                    paths.add(str(frame.resolve(strict=False)))
        return paths

    def resolve_output_path(self, printer_id: str, session_id: str, filename: str) -> Path:
        safe_printer_id = _safe_path_part(printer_id, "printer id")
        safe_session_id = _safe_path_part(session_id, "session id")
        safe_filename = _safe_filename(filename)
        root = (self._recordings_root / "timelapses").resolve(strict=False)
        output_path = (
            root / safe_printer_id / safe_session_id / safe_filename
        ).resolve(strict=False)
        try:
            output_path.relative_to(root)
        except ValueError as exc:
            raise ValueError("Invalid timelapse output path") from exc
        return output_path

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())

        for session in sessions:
            if session.state and session.state.status in ACTIVE_STATUSES:
                session.state.stop_reason = "app_shutdown"
                session.stop_event.set()

        for session in sessions:
            if session.thread and session.thread.is_alive():
                session.thread.join(timeout=2.0)

    def _run_session(self, managed: ManagedTimelapse) -> None:
        self._update_state(managed, status="running")
        next_capture_at = time.monotonic()
        next_moonraker_check_at = time.monotonic()
        stop_reason = "manual"

        while not managed.stop_event.is_set():
            now = time.monotonic()
            if now >= next_moonraker_check_at:
                auto_stop_reason = self._check_moonraker_auto_stop(managed)
                next_moonraker_check_at = time.monotonic() + max(5, min(30, managed.interval_seconds))
                if auto_stop_reason:
                    stop_reason = auto_stop_reason
                    managed.stop_event.set()
                    break

            if now >= next_capture_at:
                capture_ok = self._capture_frame(managed)
                next_capture_at = time.monotonic() + managed.interval_seconds
                if not capture_ok and managed.consecutive_capture_errors >= 3:
                    stop_reason = "capture_error"
                    managed.stop_event.set()
                    break

            managed.stop_event.wait(timeout=0.25)

        state_stop_reason = managed.state.stop_reason if managed.state else None
        self._render_after_stop(managed, state_stop_reason or stop_reason)

    def _check_moonraker_auto_stop(self, managed: ManagedTimelapse) -> str | None:
        if not managed.moonraker_url:
            return None

        status = self._moonraker_service.fetch_status(managed.moonraker_url)
        monitor_state = str(status.monitor_state or "").lower()
        status_text = status.printer_status_text or "Status unavailable"

        updates = {
            "moonraker_state": monitor_state,
            "moonraker_message": status_text,
        }
        if monitor_state in PRINTING_STATES:
            updates["observed_printing"] = True
        self._update_state(managed, **updates)

        observed_printing = bool(managed.state and managed.state.observed_printing)
        if "cancel" in status_text.lower():
            return "moonraker_cancelled"
        if monitor_state in {"error"}:
            return "moonraker_error"
        if observed_printing and monitor_state in {"complete"}:
            return "moonraker_complete"
        if observed_printing and monitor_state in {"idle"}:
            return "moonraker_idle_after_print"
        return None

    def _capture_frame(self, managed: ManagedTimelapse) -> bool:
        frame_number = (managed.state.frame_count if managed.state else 0) + 1
        frame_path = managed.frames_dir / f"frame_{frame_number:06d}.jpg"
        command = _frame_capture_command(managed.record_url, frame_path)
        LOGGER.debug(
            "Capturing timelapse frame printer=%s camera=%s command=%s",
            managed.printer_id,
            managed.camera_id,
            list2cmdline(command),
        )

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(30, min(120, managed.interval_seconds + 30)),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            managed.consecutive_capture_errors += 1
            self._update_state(managed, last_error=f"Frame capture failed: {exc}")
            LOGGER.warning("Timelapse frame capture failed for %s: %s", managed.printer_id, exc)
            return False

        if result.returncode != 0 or not frame_path.exists():
            managed.consecutive_capture_errors += 1
            stderr = (result.stderr or "").strip()
            message = _last_error_line(stderr) or f"ffmpeg exited with {result.returncode}"
            self._update_state(managed, last_error=f"Frame capture failed: {message}")
            LOGGER.warning(
                "Timelapse frame capture failed for %s (exit %s): %s",
                managed.printer_id,
                result.returncode,
                stderr or "<no stderr>",
            )
            return False

        managed.consecutive_capture_errors = 0
        self._update_state(
            managed,
            frame_count=frame_number,
            last_error=None,
        )
        return True

    def _render_after_stop(self, managed: ManagedTimelapse, stop_reason: str) -> None:
        stopped_at = datetime.utcnow()
        frame_count = managed.state.frame_count if managed.state else 0
        self._update_state(
            managed,
            status="rendering",
            stopped_at=stopped_at,
            stop_reason=stop_reason,
            render_status="running",
        )

        if frame_count <= 0:
            self._update_state(
                managed,
                status="error",
                render_status="skipped",
                last_error="No timelapse frames were captured; no MP4 was rendered.",
            )
            self._finish_session(managed)
            return

        command = _render_command(managed.frames_dir, managed.output_path)
        LOGGER.info(
            "Rendering timelapse printer=%s session=%s command=%s",
            managed.printer_id,
            managed.session_id,
            list2cmdline(command),
        )

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(120, frame_count * 5),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._update_state(
                managed,
                status="error",
                render_status="error",
                render_error=f"Render failed: {exc}",
            )
            LOGGER.error("Timelapse render failed for %s: %s", managed.printer_id, exc)
            self._finish_session(managed)
            return

        if result.returncode != 0 or not managed.output_path.exists():
            stderr = (result.stderr or "").strip()
            message = _last_error_line(stderr) or f"ffmpeg exited with {result.returncode}"
            self._update_state(
                managed,
                status="error",
                render_status="error",
                render_error=f"Render failed: {message}",
            )
            LOGGER.error(
                "Timelapse render failed for %s (exit %s): %s",
                managed.printer_id,
                result.returncode,
                stderr or "<no stderr>",
            )
            self._finish_session(managed)
            return

        self._update_state(
            managed,
            status="complete",
            render_status="complete",
            output_file=managed.output_path.name,
            output_path=str(managed.output_path),
            output_url=_download_url(managed.printer_id, managed.session_id, managed.output_path.name),
            last_error=None,
            render_error=None,
        )
        LOGGER.info(
            "Timelapse complete printer=%s session=%s frames=%s output=%s",
            managed.printer_id,
            managed.session_id,
            frame_count,
            managed.output_path,
        )
        self._finish_session(managed)

    def _finish_session(self, managed: ManagedTimelapse) -> None:
        with self._lock:
            current = self._sessions.get(managed.printer_id)
            if current is managed:
                self._sessions.pop(managed.printer_id, None)
            if managed.state:
                self._states[managed.printer_id] = managed.state

        if self._on_timelapse_finished:
            try:
                self._on_timelapse_finished()
            except Exception as exc:  # pragma: no cover - defensive callback
                LOGGER.warning("Post-timelapse callback failed: %s", exc)

    def _update_state(self, managed: ManagedTimelapse, **updates: object) -> None:
        with self._lock:
            if not managed.state:
                return
            managed.state = managed.state.model_copy(update=updates)
            self._states[managed.printer_id] = managed.state

    def _load_existing_outputs(self) -> None:
        timelapse_root = self._recordings_root / "timelapses"
        if not timelapse_root.exists():
            return

        latest_by_printer: dict[str, Path] = {}
        for output_path in timelapse_root.glob("*/*/*.mp4"):
            if not output_path.is_file():
                continue
            printer_id = output_path.parent.parent.name
            current = latest_by_printer.get(printer_id)
            try:
                output_mtime = output_path.stat().st_mtime
                current_mtime = current.stat().st_mtime if current else -1
            except OSError:
                continue
            if current is None or output_mtime > current_mtime:
                latest_by_printer[printer_id] = output_path

        for printer_id, output_path in latest_by_printer.items():
            session_id = output_path.parent.name
            frames_dir = output_path.parent / "frames"
            frame_count = len(list(frames_dir.glob("frame_*.jpg"))) if frames_dir.exists() else 0
            try:
                stopped_at = datetime.utcfromtimestamp(output_path.stat().st_mtime)
            except OSError:
                stopped_at = None
            self._states[printer_id] = TimelapseSessionState(
                printer_id=printer_id,
                status="complete",
                frame_count=frame_count,
                stopped_at=stopped_at,
                stop_reason="previous_session",
                session_id=session_id,
                frames_dir=str(frames_dir),
                output_file=output_path.name,
                output_path=str(output_path),
                output_url=_download_url(printer_id, session_id, output_path.name),
                render_status="complete",
            )


def _frame_capture_command(record_url: str, frame_path: Path) -> list[str]:
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if record_url.lower().startswith("rtsp://"):
        command.extend(["-rtsp_transport", "tcp"])
    command.extend([
        "-i",
        record_url,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(frame_path),
    ])
    return command


def _render_command(frames_dir: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        "30",
        "-i",
        str(frames_dir / "frame_%06d.jpg"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _safe_path_part(value: str, label: str) -> str:
    if not SAFE_PATH_RE.match(value) or value in {".", ".."}:
        raise ValueError(f"Invalid {label}")
    return value


def _safe_filename(value: str) -> str:
    path = Path(value)
    if path.name != value or value in {".", ".."}:
        raise ValueError("Invalid filename")
    if not value.lower().endswith(".mp4"):
        raise ValueError("Timelapse output must be an MP4 file")
    return value


def _unique_session_id(printer_id: str, started_at: datetime) -> str:
    return f"{printer_id}_{started_at.strftime('%Y%m%d_%H%M%S_%f')}"


def _download_url(printer_id: str, session_id: str, filename: str) -> str:
    return (
        f"/api/timelapse/download/"
        f"{quote(printer_id, safe='')}/"
        f"{quote(session_id, safe='')}/"
        f"{quote(filename, safe='')}"
    )


def _last_error_line(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return lines[-1] if lines else ""
