from __future__ import annotations

from threading import Lock
from hashlib import sha256
from pathlib import Path

from app.config import (
    build_camera_input,
    build_management_items,
    config_uses_printer_first,
    load_camera_inputs,
    load_printer_config_inputs,
    normalize_printer_config_inputs,
    printer_camera_config_from_camera_input,
    validate_camera_inputs,
    write_camera_inputs,
    write_printer_config_inputs,
)
from app.models import (
    CameraConfigInput,
    CameraManagementItem,
    CameraUpsertRequest,
    PrinterConfigInput,
    ResolvedCamera,
)


class CameraConfigStore:
    def __init__(self, config_path: str) -> None:
        self._config_path = config_path
        self._lock = Lock()

    def revision(self) -> str:
        try:
            return sha256(Path(self._config_path).read_bytes()).hexdigest()
        except FileNotFoundError:
            return sha256(b"").hexdigest()

    def list_cameras(self) -> tuple[list[CameraConfigInput], list[ResolvedCamera], list[CameraManagementItem]]:
        with self._lock:
            raw_cameras = load_camera_inputs(self._config_path)
        resolved = validate_camera_inputs(raw_cameras)
        items = build_management_items(raw_cameras, resolved)
        return raw_cameras, resolved, items

    def list_printers(self) -> tuple[list[PrinterConfigInput], list[CameraConfigInput], list[ResolvedCamera]]:
        with self._lock:
            printers = load_printer_config_inputs(self._config_path)
            raw_cameras = load_camera_inputs(self._config_path)
            resolved = validate_camera_inputs(raw_cameras)
        return printers, raw_cameras, resolved

    def save_printers(
        self,
        printers: list[PrinterConfigInput],
    ) -> tuple[list[PrinterConfigInput], list[CameraConfigInput], list[ResolvedCamera]]:
        with self._lock:
            normalized_printers = normalize_printer_config_inputs(printers)
            write_printer_config_inputs(self._config_path, normalized_printers)
            raw_cameras = load_camera_inputs(self._config_path)
            resolved = validate_camera_inputs(raw_cameras)
        return normalized_printers, raw_cameras, resolved

    def create_camera(
        self,
        payload: CameraUpsertRequest,
    ) -> tuple[list[CameraConfigInput], list[ResolvedCamera], list[CameraManagementItem]]:
        with self._lock:
            prefer_printer_config = config_uses_printer_first(self._config_path)
            raw_cameras = load_camera_inputs(self._config_path)
            new_camera = build_camera_input(payload)
            if prefer_printer_config:
                return self._mutate_nested(new_camera=new_camera)
            raw_cameras.append(_with_printer_display_order(new_camera, raw_cameras))
            resolved = validate_camera_inputs(raw_cameras)
            write_camera_inputs(
                self._config_path,
                raw_cameras,
                prefer_printer_config=prefer_printer_config,
            )
        items = build_management_items(raw_cameras, resolved)
        return raw_cameras, resolved, items

    def update_camera(
        self,
        camera_id: str,
        payload: CameraUpsertRequest,
    ) -> tuple[list[CameraConfigInput], list[ResolvedCamera], list[CameraManagementItem]]:
        with self._lock:
            prefer_printer_config = config_uses_printer_first(self._config_path)
            raw_cameras = load_camera_inputs(self._config_path)
            if prefer_printer_config:
                existing = next((camera for camera in raw_cameras if camera.id == camera_id), None)
                if existing is None:
                    raise KeyError(f"Unknown camera '{camera_id}'")
                updated_payload = payload.model_copy(update={
                    "id": payload.id or existing.id,
                    "output_subdir": payload.output_subdir or existing.output_subdir,
                })
                camera = build_camera_input(updated_payload)
                return self._mutate_nested(camera_id, camera, camera.printer_id if payload.printer_id else None)
            updated_camera = _with_printer_display_order(
                build_camera_input(payload),
                raw_cameras,
                existing_camera_id=camera_id,
            )
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
            write_camera_inputs(
                self._config_path,
                new_cameras,
                prefer_printer_config=prefer_printer_config,
            )
        items = build_management_items(new_cameras, resolved)
        return new_cameras, resolved, items

    def delete_camera(
        self,
        camera_id: str,
    ) -> tuple[list[CameraConfigInput], list[ResolvedCamera], list[CameraManagementItem]]:
        with self._lock:
            prefer_printer_config = config_uses_printer_first(self._config_path)
            raw_cameras = load_camera_inputs(self._config_path)
            if prefer_printer_config:
                return self._mutate_nested(camera_id)
            new_cameras = [camera for camera in raw_cameras if camera.id != camera_id]
            if len(new_cameras) == len(raw_cameras):
                raise KeyError(f"Unknown camera '{camera_id}'")
            resolved = validate_camera_inputs(new_cameras)
            write_camera_inputs(
                self._config_path,
                new_cameras,
                prefer_printer_config=prefer_printer_config,
            )
        items = build_management_items(new_cameras, resolved)
        return new_cameras, resolved, items

    def _mutate_nested(
        self,
        old_id: str | None = None,
        new_camera: CameraConfigInput | None = None,
        requested_printer_id: str | None = None,
    ) -> tuple[list[CameraConfigInput], list[ResolvedCamera], list[CameraManagementItem]]:
        printers = {p.id: p for p in load_printer_config_inputs(self._config_path)}
        current = next((p for p in printers.values() if any(c.id == old_id for c in p.cameras)), None)
        if old_id is not None and current is None:
            raise KeyError(f"Unknown camera '{old_id}'")
        if current:
            printers[current.id] = current.model_copy(update={
                "cameras": [c for c in current.cameras if c.id != old_id],
            })
        if new_camera is not None:
            target_id = requested_printer_id or (current.id if current else new_camera.printer_id or new_camera.id)
            target = printers.get(target_id) or PrinterConfigInput(
                id=target_id, name=new_camera.printer_name or new_camera.name,
                moonraker_url=new_camera.moonraker_url,
            )
            default_id = target.default_camera_id
            if new_camera.default_live_view or (current and current.id == target_id and default_id == old_id):
                default_id = new_camera.id
            printers[target_id] = target.model_copy(update={
                "cameras": [*target.cameras, printer_camera_config_from_camera_input(new_camera)],
                "default_camera_id": default_id,
            })
        write_printer_config_inputs(self._config_path, list(printers.values()))
        raw = load_camera_inputs(self._config_path)
        resolved = validate_camera_inputs(raw)
        return raw, resolved, build_management_items(raw, resolved)


def _with_printer_display_order(
    camera: CameraConfigInput,
    existing_cameras: list[CameraConfigInput],
    existing_camera_id: str | None = None,
) -> CameraConfigInput:
    printer_id = (camera.printer_id or "").strip() or camera.id
    for existing_camera in existing_cameras:
        existing_printer_id = (existing_camera.printer_id or "").strip() or existing_camera.id
        if existing_printer_id == printer_id and existing_camera.printer_display_order is not None:
            return camera.model_copy(
                update={"printer_display_order": existing_camera.printer_display_order}
            )

    for existing_camera in existing_cameras:
        if existing_camera.id == existing_camera_id:
            if existing_camera.printer_display_order is not None:
                return camera.model_copy(
                    update={"printer_display_order": existing_camera.printer_display_order}
                )
    return camera
