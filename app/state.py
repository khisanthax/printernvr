from __future__ import annotations

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
            return list(self._states.values())

    def get_state(self, camera_id: str) -> CameraRuntimeState | None:
        with self._lock:
            return self._states.get(camera_id)

    def as_payload(self) -> list[dict]:
        with self._lock:
            return [state.model_dump(mode="json") for state in self._states.values()]
