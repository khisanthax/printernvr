from __future__ import annotations

from datetime import datetime
from threading import Lock

from app.models import CameraRuntimeState, ResolvedCamera


class RuntimeStateManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._states: dict[str, CameraRuntimeState] = {}

    def initialize(self, cameras: list[ResolvedCamera]) -> None:
        with self._lock:
            self._states = {
                camera.id: CameraRuntimeState(camera_id=camera.id, status="idle")
                for camera in cameras
            }

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
        output_file: str,
        output_path: str,
    ) -> CameraRuntimeState:
        with self._lock:
            state = self._require_state(camera_id)
            state.status = "recording"
            state.recording = True
            state.started_at = started_at
            state.expected_end_at = expected_end_at
            state.output_file = output_file
            state.output_path = output_path
            state.last_error = None
            return state.model_copy(deep=True)

    def mark_stopping(self, camera_id: str) -> CameraRuntimeState:
        with self._lock:
            state = self._require_state(camera_id)
            state.status = "stopping"
            return state.model_copy(deep=True)

    def mark_recording_stopped(
        self,
        camera_id: str,
        last_completed_output: str | None = None,
    ) -> CameraRuntimeState:
        with self._lock:
            state = self._require_state(camera_id)
            state.status = "idle"
            state.recording = False
            state.started_at = None
            state.expected_end_at = None
            state.output_file = None
            state.output_path = None
            if last_completed_output:
                state.last_completed_output = last_completed_output
            return state.model_copy(deep=True)

    def mark_error(self, camera_id: str, message: str) -> CameraRuntimeState:
        with self._lock:
            state = self._require_state(camera_id)
            state.status = "error"
            state.recording = False
            state.started_at = None
            state.expected_end_at = None
            state.output_file = None
            state.output_path = None
            state.last_error = message
            return state.model_copy(deep=True)

    def clear_error(self, camera_id: str) -> CameraRuntimeState:
        with self._lock:
            state = self._require_state(camera_id)
            state.last_error = None
            if not state.recording:
                state.status = "idle"
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
