from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
from typing import Callable

from app.models import CameraRuntimeState, ResolvedCamera
from app.state import RuntimeStateManager

LOGGER = logging.getLogger(__name__)


@dataclass
class ManagedRecording:
    camera_id: str
    process: subprocess.Popen[str]
    output_file: str
    output_path: str
    started_at: datetime
    expected_end_at: datetime | None
    stop_requested: bool = False
    stderr_output: str = ""
    monitor_thread: Thread | None = None


class RecordingManager:
    def __init__(
        self,
        recordings_root: str,
        runtime_state: RuntimeStateManager,
        on_recording_finished: Callable[[], None] | None = None,
    ) -> None:
        self._recordings_root = Path(recordings_root)
        self._runtime_state = runtime_state
        self._on_recording_finished = on_recording_finished
        self._lock = Lock()
        self._processes: dict[str, ManagedRecording] = {}

    def start_recording(
        self,
        camera: ResolvedCamera,
        duration: int | None = None,
    ) -> CameraRuntimeState:
        if not camera.enabled:
            raise ValueError(f"Camera '{camera.id}' is disabled")

        with self._lock:
            current = self._processes.get(camera.id)
            if current and current.process.poll() is None:
                raise ValueError(f"Camera '{camera.id}' is already recording")

        output_dir = self._recordings_root / camera.output_subdir
        output_dir.mkdir(parents=True, exist_ok=True)

        started_at = datetime.utcnow()
        expected_end_at = (
            started_at + timedelta(seconds=duration) if duration is not None else None
        )
        output_file = f"{camera.id}_{started_at.strftime('%Y%m%d_%H%M%S')}.mp4"
        output_path = str(output_dir / output_file)
        command = self._build_ffmpeg_command(camera.record_url, output_path, duration)

        LOGGER.info("Starting recording for %s -> %s", camera.id, output_path)

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            self._runtime_state.mark_error(camera.id, f"ffmpeg start failed: {exc}")
            raise RuntimeError(f"Unable to start ffmpeg for {camera.id}: {exc}") from exc

        managed = ManagedRecording(
            camera_id=camera.id,
            process=process,
            output_file=output_file,
            output_path=output_path,
            started_at=started_at,
            expected_end_at=expected_end_at,
        )

        self._runtime_state.mark_recording_started(
            camera.id,
            started_at=started_at,
            expected_end_at=expected_end_at,
            output_file=output_file,
            output_path=output_path,
        )

        monitor_thread = Thread(
            target=self._monitor_recording,
            args=(managed,),
            daemon=True,
            name=f"recording-monitor-{camera.id}",
        )
        managed.monitor_thread = monitor_thread

        with self._lock:
            self._processes[camera.id] = managed

        monitor_thread.start()
        return self._runtime_state.get_state(camera.id)  # type: ignore[return-value]

    def stop_recording(self, camera_id: str) -> CameraRuntimeState:
        with self._lock:
            managed = self._processes.get(camera_id)
            if not managed or managed.process.poll() is not None:
                raise ValueError(f"Camera '{camera_id}' is not currently recording")
            managed.stop_requested = True

        self._runtime_state.mark_stopping(camera_id)
        LOGGER.info("Stopping recording for %s", camera_id)

        try:
            managed.process.terminate()
        except OSError as exc:
            LOGGER.warning("Terminate failed for %s: %s", camera_id, exc)
            try:
                managed.process.kill()
            except OSError:
                pass

        return self._runtime_state.get_state(camera_id)  # type: ignore[return-value]

    def is_recording(self, camera_id: str) -> bool:
        with self._lock:
            managed = self._processes.get(camera_id)
            return bool(managed and managed.process.poll() is None)

    def shutdown(self) -> None:
        with self._lock:
            active = list(self._processes.values())

        for managed in active:
            if managed.process.poll() is None:
                managed.stop_requested = True
                try:
                    managed.process.terminate()
                except OSError:
                    try:
                        managed.process.kill()
                    except OSError:
                        pass

    def _build_ffmpeg_command(
        self,
        record_url: str,
        output_path: str,
        duration: int | None,
    ) -> list[str]:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            record_url,
            "-vcodec",
            "copy",
            "-acodec",
            "copy",
        ]
        if duration is not None:
            command.extend(["-t", str(duration)])
        command.append(output_path)
        return command

    def _monitor_recording(self, managed: ManagedRecording) -> None:
        _stdout, stderr_output = managed.process.communicate()
        exit_code = managed.process.returncode or 0
        managed.stderr_output = (stderr_output or "").strip()

        with self._lock:
            current = self._processes.get(managed.camera_id)
            if current is managed:
                self._processes.pop(managed.camera_id, None)

        if managed.stop_requested or exit_code == 0:
            self._runtime_state.mark_recording_stopped(
                managed.camera_id,
                last_completed_output=managed.output_file,
            )
            LOGGER.info(
                "Recording finished for %s -> %s",
                managed.camera_id,
                managed.output_path,
            )
        else:
            error_message = self._extract_error_message(exit_code, managed.stderr_output)
            self._runtime_state.mark_error(managed.camera_id, error_message)
            LOGGER.error(
                "Recording failed for %s (exit %s): %s",
                managed.camera_id,
                exit_code,
                error_message,
            )

        if managed.stderr_output:
            LOGGER.debug("ffmpeg stderr for %s: %s", managed.camera_id, managed.stderr_output)

        if self._on_recording_finished:
            try:
                self._on_recording_finished()
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Post-recording callback failed: %s", exc)

    def _extract_error_message(self, exit_code: int, stderr_output: str) -> str:
        if stderr_output:
            lines = [line.strip() for line in stderr_output.splitlines() if line.strip()]
            if lines:
                return lines[-1]
        return f"ffmpeg exited with code {exit_code}"
