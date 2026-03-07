from __future__ import annotations

from threading import Lock

from app.config import (
    build_camera_input,
    build_management_items,
    load_camera_inputs,
    validate_camera_inputs,
    write_camera_inputs,
)
from app.models import CameraConfigInput, CameraManagementItem, CameraUpsertRequest, ResolvedCamera


class CameraConfigStore:
    def __init__(self, config_path: str) -> None:
        self._config_path = config_path
        self._lock = Lock()

    def list_cameras(self) -> tuple[list[CameraConfigInput], list[ResolvedCamera], list[CameraManagementItem]]:
        with self._lock:
            raw_cameras = load_camera_inputs(self._config_path)
        resolved = validate_camera_inputs(raw_cameras)
        items = build_management_items(raw_cameras, resolved)
        return raw_cameras, resolved, items

    def create_camera(
        self,
        payload: CameraUpsertRequest,
    ) -> tuple[list[CameraConfigInput], list[ResolvedCamera], list[CameraManagementItem]]:
        with self._lock:
            raw_cameras = load_camera_inputs(self._config_path)
            raw_cameras.append(build_camera_input(payload))
            resolved = validate_camera_inputs(raw_cameras)
            write_camera_inputs(self._config_path, raw_cameras)
        items = build_management_items(raw_cameras, resolved)
        return raw_cameras, resolved, items

    def update_camera(
        self,
        camera_id: str,
        payload: CameraUpsertRequest,
    ) -> tuple[list[CameraConfigInput], list[ResolvedCamera], list[CameraManagementItem]]:
        with self._lock:
            raw_cameras = load_camera_inputs(self._config_path)
            updated_camera = build_camera_input(payload)
            updated = False
            new_cameras: list[CameraConfigInput] = []
            for camera in raw_cameras:
                if camera.id == camera_id:
                    new_cameras.append(updated_camera)
                    updated = True
                else:
                    new_cameras.append(camera)
            if not updated:
                raise KeyError(f"Unknown camera '{camera_id}'")
            resolved = validate_camera_inputs(new_cameras)
            write_camera_inputs(self._config_path, new_cameras)
        items = build_management_items(new_cameras, resolved)
        return new_cameras, resolved, items

    def delete_camera(
        self,
        camera_id: str,
    ) -> tuple[list[CameraConfigInput], list[ResolvedCamera], list[CameraManagementItem]]:
        with self._lock:
            raw_cameras = load_camera_inputs(self._config_path)
            new_cameras = [camera for camera in raw_cameras if camera.id != camera_id]
            if len(new_cameras) == len(raw_cameras):
                raise KeyError(f"Unknown camera '{camera_id}'")
            resolved = validate_camera_inputs(new_cameras)
            write_camera_inputs(self._config_path, new_cameras)
        items = build_management_items(new_cameras, resolved)
        return new_cameras, resolved, items
