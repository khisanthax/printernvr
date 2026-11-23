from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from subprocess import list2cmdline
from threading import Event, Lock, Thread
from typing import Callable
from uuid import uuid4

from app.media import publish_media, redact_diagnostic, validate_mp4
from app.models import CameraRuntimeState, ResolvedCamera
from app.state import RuntimeStateManager

LOGGER = logging.getLogger(__name__)


@dataclass
class ManagedRecording:
    camera: ResolvedCamera
    staged: Path
    final: Path
    duration: int | None
    frame_zero_at: datetime | None = None
    stop: Event = field(default_factory=Event)
    worker: Thread | None = None


class RecordingManager:
    def __init__(
        self,
        recordings_root: str,
        runtime_state: RuntimeStateManager,
        on_recording_finished: Callable[[], None] | None = None,
        *,
        quit_timeout: float = 8,
        minimum_free_bytes: int = 64 * 1024**2,
        max_duration: int = 600,
        save_recording_anchor: Callable[[str, str, dict], None] | None = None,
    ) -> None:
        self._recordings_root = Path(recordings_root).resolve()
        self._runtime_state = runtime_state
        self._on_recording_finished = on_recording_finished
        self._quit_timeout = quit_timeout
        self._minimum_free_bytes = minimum_free_bytes
        self._max_duration = max_duration
        self._save_recording_anchor = save_recording_anchor
        self._lock = Lock()
        self._processes: dict[str, ManagedRecording] = {}
        self._closing = False

    def start_recording(
        self, camera: ResolvedCamera, duration: int | None = None,
    ) -> CameraRuntimeState:
        if not camera.enabled or camera.backend_type != "ffmpeg" or not camera.record_url:
            raise ValueError(f"Camera '{camera.id}' has no enabled FFmpeg input")
        if duration is not None and not 1 <= duration <= self._max_duration:
            raise ValueError(f"Duration must be between 1 and {self._max_duration} seconds")
        output_dir = (self._recordings_root / camera.output_subdir).resolve()
        if output_dir.parent != self._recordings_root or output_dir.name == "timelapses":
            raise ValueError("Invalid camera output directory")

        with self._lock:
            if self._closing:
                raise ValueError("Recorder is shutting down")
            if camera.id in self._processes:
                raise ValueError(f"Camera '{camera.id}' already has a recording in progress")
            output_dir.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(output_dir).free < self._minimum_free_bytes:
                raise ValueError("Insufficient free space to start recording")

            started = datetime.now(timezone.utc)
            final = output_dir / f"{camera.id}_{started:%Y%m%d_%H%M%S}_{uuid4().hex}.mp4"
            staged = final.with_suffix(".mp4.part")
            staged.touch(exist_ok=False)
            job = ManagedRecording(camera, staged, final, duration)
            self._processes[camera.id] = job
            snapshot = self._runtime_state.update_state(
                camera.id, status="starting", in_progress_action="starting",
                recording=False, started_at=started,
                expected_end_at=started + timedelta(seconds=duration) if duration else None,
                output_file=final.name, output_path=str(final),
                requested_duration_seconds=duration, last_error=None,
                last_error_details=None, last_ffmpeg_command=None, last_ffmpeg_exit_code=None,
                last_action_message="Starting FFmpeg",
            )
            job.worker = Thread(target=self._record, args=(job,), daemon=True, name=f"record-{camera.id}")
            try:
                job.worker.start()
            except RuntimeError:
                self._processes.pop(camera.id)
                staged.unlink(missing_ok=True)
                self._runtime_state.mark_error(camera.id, "Unable to start recording worker")
                raise
            return snapshot

    def stop_recording(self, camera_id: str) -> CameraRuntimeState:
        with self._lock:
            job = self._processes.get(camera_id)
            if job:
                job.stop.set()
                state = self._runtime_state.get_state(camera_id)
                if state is not None and state.status in {"starting", "recording"}:
                    self._runtime_state.mark_stopping(camera_id, "Requesting graceful FFmpeg stop")
            state = self._runtime_state.get_state(camera_id)
            if state is None:
                raise ValueError(f"Unknown camera '{camera_id}'")
            return state

    def is_recording(self, camera_id: str) -> bool:
        with self._lock:
            return camera_id in self._processes

    def shutdown(self) -> None:
        with self._lock:
            self._closing = True
            jobs = list(self._processes.values())
            for job in jobs:
                job.stop.set()
        deadline = time.monotonic() + self._quit_timeout + 18
        for job in jobs:
            if job.worker is not None:
                job.worker.join(max(0, deadline - time.monotonic()))

    def _build_ffmpeg_command(self, record_url: str, output_path: str, duration: int | None) -> list[str]:
        command = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
                   "-stats_period", "0.25", "-progress", "pipe:1", "-y"]
        if record_url.lower().startswith("rtsp://"):
            command.extend(["-rtsp_transport", "tcp", "-timeout", "15000000"])
        command.extend(["-i", record_url, "-map", "0:v:0", "-an", "-c:v", "copy"])
        if duration is not None:
            command.extend(["-t", str(duration)])
        return [*command, "-f", "mp4", output_path]

    def _record(self, job: ManagedRecording) -> None:
        camera_id = job.camera.id
        url = job.camera.record_url or ""
        command = self._build_ffmpeg_command(url, str(job.staged), job.duration)
        tail = bytearray()
        drain: Thread | None = None
        progress: Thread | None = None
        process: subprocess.Popen[bytes] | None = None
        published = False

        def read_stderr() -> None:
            stream = process.stderr
            try:
                while chunk := stream.read1(4096):
                    tail.extend(chunk)
                    del tail[:-16384]
            except OSError:
                pass

        def read_progress() -> None:
            try:
                for line in process.stdout:
                    if job.frame_zero_at is None and line.startswith(b"out_time_us="):
                        try:
                            microseconds = int(line.split(b"=", 1)[1])
                            if microseconds > 0:
                                job.frame_zero_at = datetime.now(timezone.utc) - timedelta(microseconds=microseconds)
                        except (ValueError, OverflowError):
                            continue
            except OSError:
                pass

        try:
            if job.stop.is_set():
                raise RuntimeError("Recording cancelled before FFmpeg started")
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
            )
            drain = Thread(target=read_stderr, daemon=True)
            drain.start()
            progress = Thread(target=read_progress, daemon=True)
            progress.start()
            with self._lock:
                if not job.stop.is_set():
                    self._runtime_state.update_state(
                        camera_id, status="recording", in_progress_action="recording",
                        recording=True, last_action_message="FFmpeg recording active",
                    )
            deadline = time.monotonic() + job.duration + 45 if job.duration else None
            requested_stop = False
            next_disk_check = time.monotonic()
            while process.poll() is None:
                now = time.monotonic()
                low_disk = False
                if now >= next_disk_check:
                    low_disk = shutil.disk_usage(job.staged.parent).free < self._minimum_free_bytes
                    next_disk_check = now + 2
                if job.stop.is_set() or low_disk:
                    requested_stop = True
                    self._runtime_state.mark_stopping(
                        camera_id, "Stopping because recording storage is low" if low_disk else "Flushing recording",
                    )
                    if not self._quit(process):
                        raise RuntimeError("FFmpeg did not stop gracefully before the deadline")
                    break
                if deadline is not None and now >= deadline:
                    raise RuntimeError("Timed recording exceeded its wall-clock deadline")
                job.stop.wait(0.1)

            self._runtime_state.mark_stopping(camera_id, "Validating recording")
            if process.returncode != 0:
                raise RuntimeError(f"FFmpeg exited with code {process.returncode}")
            if not requested_stop and not job.stop.is_set() and job.duration is None:
                raise RuntimeError("Recording input ended unexpectedly")
            validate_mp4(job.staged)
            publish_media(job.staged, job.final)
            published = True
            progress.join(timeout=1)
            if self._save_recording_anchor and job.frame_zero_at:
                try:
                    self._save_recording_anchor(camera_id, job.final.name, {
                        "frame_zero_at": job.frame_zero_at.isoformat(),
                        "method": "ffmpeg-progress-estimate",
                    })
                except (OSError, ValueError):
                    LOGGER.warning("Unable to save video time anchor for %s", camera_id)
            self._runtime_state.mark_recording_stopped(
                camera_id, last_completed_output=job.final.name, message="Recording complete",
            )
        except (OSError, RuntimeError, ValueError) as exc:
            if process is not None:
                self._terminate(process)
            if drain is not None:
                drain.join(timeout=1)
            details = redact_diagnostic(tail.decode("utf-8", errors="replace").strip(), url)
            self._runtime_state.mark_error(
                camera_id, redact_diagnostic(str(exc), url), details=details or None,
                ffmpeg_command=redact_diagnostic(list2cmdline(command), url),
                exit_code=process.returncode if process else None,
            )
            LOGGER.warning("Recording failed for %s: %s", camera_id, redact_diagnostic(str(exc), url))
        finally:
            if process is not None:
                if drain is not None:
                    drain.join(timeout=1)
                if progress is not None:
                    progress.join(timeout=1)
                for stream in (process.stdin, process.stderr, process.stdout):
                    if stream is not None:
                        stream.close()
            try:
                job.staged.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Unable to remove recording staging file for %s", camera_id)
            finally:
                with self._lock:
                    self._processes.pop(camera_id, None)

        if published and self._on_recording_finished:
            try:
                self._on_recording_finished()
            except Exception:
                LOGGER.exception("Post-recording callback failed")

    def _quit(self, process: subprocess.Popen[bytes]) -> bool:
        try:
            if process.stdin is not None:
                process.stdin.write(b"q\n")
                process.stdin.flush()
            process.wait(timeout=self._quit_timeout)
            return True
        except (OSError, subprocess.TimeoutExpired):
            self._terminate(process)
            return False

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        for signal in (process.terminate, process.kill):
            try:
                signal()
                process.wait(timeout=2)
                return
            except (OSError, subprocess.TimeoutExpired):
                continue
