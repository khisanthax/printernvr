from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Any

from app.models import CameraRuntimeState, ResolvedCamera


class RuntimeStateManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._states: dict[str, CameraRuntimeState] = {}

    def initialize(self, cameras: list[ResolvedCamera]) -> None:
        with self._lock:
            self._states = {
                camera.id: CameraRuntimeState(
                    camera_id=camera.id,
                    backend_type=camera.backend_type,
                )
                for camera in cameras
            }

    def sync_cameras(self, cameras: list[ResolvedCamera]) -> None:
        with self._lock:
            synced_states: dict[str, CameraRuntimeState] = {}
            for camera in cameras:
                existing = self._states.get(camera.id)
                if existing and existing.backend_type == camera.backend_type:
                    existing.backend_type = camera.backend_type
                    synced_states[camera.id] = existing
                else:
                    synced_states[camera.id] = CameraRuntimeState(
                        camera_id=camera.id,
                        backend_type=camera.backend_type,
                    )
            self._states = synced_states

    def list_states(self) -> list[CameraRuntimeState]:
        with self._lock:
            return [state.model_copy(deep=True) for state in self._states.values()]

    def get_state(self, camera_id: str) -> CameraRuntimeState | None:
        with self._lock:
            state = self._states.get(camera_id)
            return state.model_copy(deep=True) if state else None

    def as_payload(self) -> list[dict]:
        with self._lock:
            return [state.model_dump(mode="json") for state in self._states.values()]

    def mark_recording_started(
        self,
        camera_id: str,
        started_at: datetime,
        expected_end_at: datetime | None,
        output_file: str | None = None,
        output_path: str | None = None,
        requested_duration_seconds: int | None = None,
        message: str | None = None,
    ) -> CameraRuntimeState:
        return self.update_state(
            camera_id,
            status="recording",
            in_progress_action="recording",
            recording=True,
            started_at=started_at,
            expected_end_at=expected_end_at,
            output_file=output_file,
            output_path=output_path,
            requested_duration_seconds=requested_duration_seconds,
            last_error=None,
            last_error_details=None,
            last_ffmpeg_command=None,
            last_ffmpeg_exit_code=None,
            last_action_message=message,
        )

    def mark_starting(
        self,
        camera_id: str,
        requested_duration_seconds: int | None = None,
        message: str | None = None,
    ) -> CameraRuntimeState:
        return self.update_state(
            camera_id,
            status="starting",
            in_progress_action="starting",
            recording=False,
            requested_duration_seconds=requested_duration_seconds,
            last_error=None,
            last_error_details=None,
            last_action_message=message,
        )

    def mark_stopping(self, camera_id: str, message: str | None = None) -> CameraRuntimeState:
        return self.update_state(
            camera_id,
            status="stopping",
            in_progress_action="stopping",
            recording=False,
            last_action_message=message,
        )

    def mark_downloading(self, camera_id: str, message: str | None = None) -> CameraRuntimeState:
        return self.update_state(
            camera_id,
            status="downloading",
            in_progress_action="downloading",
            recording=False,
            output_file=None,
            output_path=None,
            last_action_message=message,
        )

    def mark_recording_stopped(
        self,
        camera_id: str,
        last_completed_output: str | None = None,
        last_downloaded_filename: str | None = None,
        last_download_status: str | None = None,
        message: str | None = None,
    ) -> CameraRuntimeState:
        updates: dict[str, Any] = {
            "status": "idle",
            "in_progress_action": "idle",
            "recording": False,
            "started_at": None,
            "expected_end_at": None,
            "requested_duration_seconds": None,
            "output_file": None,
            "output_path": None,
            "last_error": None,
            "last_error_details": None,
            "last_ffmpeg_command": None,
            "last_ffmpeg_exit_code": None,
            "last_action_message": message,
        }
        if last_completed_output is not None:
            updates["last_completed_output"] = last_completed_output
        if last_downloaded_filename is not None:
            updates["last_downloaded_filename"] = last_downloaded_filename
        if last_download_status is not None:
            updates["last_download_status"] = last_download_status
        return self.update_state(camera_id, **updates)

    def mark_error(
        self,
        camera_id: str,
        message: str,
        details: str | None = None,
        ffmpeg_command: str | None = None,
        exit_code: int | None = None,
        last_download_status: str | None = None,
    ) -> CameraRuntimeState:
        return self.update_state(
            camera_id,
            status="error",
            in_progress_action="error",
            recording=False,
            started_at=None,
            expected_end_at=None,
            requested_duration_seconds=None,
            output_file=None,
            output_path=None,
            last_error=message,
            last_error_details=details,
            last_ffmpeg_command=ffmpeg_command,
            last_ffmpeg_exit_code=exit_code,
            last_download_status=last_download_status,
            last_action_message=message,
        )

    def clear_error(self, camera_id: str) -> CameraRuntimeState:
        state = self.get_state(camera_id)
        if not state:
            raise KeyError(f"Unknown camera_id: {camera_id}")
        return self.update_state(
            camera_id,
            last_error=None,
            last_error_details=None,
            last_ffmpeg_command=None,
            last_ffmpeg_exit_code=None,
            last_action_message=None if not state.recording else state.last_action_message,
            status="idle" if not state.recording else state.status,
            in_progress_action="idle" if not state.recording else state.in_progress_action,
        )

    def update_state(self, camera_id: str, **changes: Any) -> CameraRuntimeState:
        with self._lock:
            state = self._require_state(camera_id)
            for field_name, value in changes.items():
                setattr(state, field_name, value)
            return state.model_copy(deep=True)

    def active_output_paths(self) -> set[str]:
        with self._lock:
            return {
                state.output_path
                for state in self._states.values()
                if state.recording and state.output_path
            }

    def _require_state(self, camera_id: str) -> CameraRuntimeState:
        state = self._states.get(camera_id)
        if not state:
            raise KeyError(f"Unknown camera_id: {camera_id}")
        return state
