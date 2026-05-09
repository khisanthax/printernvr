from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from app.models import (
    AppConfig,
    AppSettingsFile,
    CameraConfigFile,
    CameraConfigInput,
    CameraManagementItem,
    CameraMode,
    CameraPreviewMode,
    CameraUpsertRequest,
    PrinterCameraConfigInput,
    PrinterConfigInput,
    ResolvedCamera,
    infer_input_mode,
)


def generate_go2rtc_urls(
    go2rtc_base_url: str,
    stream_name: str | None = None,
) -> tuple[str, str]:
    raw_base = go2rtc_base_url.strip()
    if "://" not in raw_base:
        raw_base = f"http://{raw_base}"

    parsed = urlparse(raw_base)
    if not parsed.hostname:
        raise ValueError(f"Invalid go2rtc_base_url: {go2rtc_base_url}")

    stream = (stream_name or "cam").strip() or "cam"
    stream_q = quote_plus(stream)

    http_scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "http"
    preview_base = f"{http_scheme}://{parsed.netloc}"
    base_path = parsed.path.rstrip("/")
    if base_path and base_path != "/":
        preview_base = f"{preview_base}{base_path}"

    preview_url = f"{preview_base}/stream.html?src={stream_q}"
    record_url = f"rtsp://{parsed.hostname}:8554/{stream}"
    return preview_url, record_url


def resolve_camera(camera: CameraConfigInput) -> ResolvedCamera:
    mode = infer_input_mode(camera)
    printer_id = (camera.printer_id or "").strip() or camera.id
    printer_name = (camera.printer_name or "").strip() or camera.name
    moonraker_url = (camera.moonraker_url or "").strip() or None

    if mode == "gopro":
        preview_mode = _effective_preview_mode(camera.preview_mode)
        preview_url = (camera.preview_url or "").strip() or None
        return ResolvedCamera(
            id=camera.id,
            name=camera.name,
            enabled=camera.enabled,
            description=camera.description,
            mode="gopro",
            backend_type="gopro",
            printer_id=printer_id,
            printer_name=printer_name,
            default_live_view=camera.default_live_view,
            moonraker_url=moonraker_url,
            printer_display_order=camera.printer_display_order,
            display_order=camera.display_order,
            preview_url=preview_url if preview_mode == "external_link" else None,
            record_url=None,
            gopro_host=(camera.gopro_host or "").strip() or None,
            preview_mode=preview_mode,
            auto_download_after_stop=camera.auto_download_after_stop,
            download_timeout_seconds=camera.download_timeout_seconds,
            file_stabilization_wait_seconds=camera.file_stabilization_wait_seconds,
            output_subdir=camera.output_subdir or camera.id,
        )

    generated_preview: str | None = None
    generated_record: str | None = None

    if camera.go2rtc_base_url:
        generated_preview, generated_record = generate_go2rtc_urls(
            camera.go2rtc_base_url,
            camera.stream_name,
        )

    final_record_url = (camera.record_url or generated_record or "").strip() or None
    final_preview_url = (camera.preview_url or generated_preview or "").strip() or None

    if not final_record_url:
        raise ValueError(f"Camera '{camera.id}' could not resolve final record_url")

    return ResolvedCamera(
        id=camera.id,
        name=camera.name,
        enabled=camera.enabled,
        description=camera.description,
        mode=mode,
        backend_type="ffmpeg",
        printer_id=printer_id,
        printer_name=printer_name,
        default_live_view=camera.default_live_view,
        moonraker_url=moonraker_url,
        display_order=camera.display_order,
        go2rtc_base_url=camera.go2rtc_base_url,
        stream_name=camera.stream_name,
        preview_url=final_preview_url,
        record_url=final_record_url,
        output_subdir=camera.output_subdir or camera.id,
    )


def load_app_config(camera_config_path: str, app_settings_path: str) -> AppConfig:
    cameras = load_camera_config(camera_config_path)
    settings = load_app_settings(app_settings_path)
    return AppConfig(cameras=cameras, retention=settings.retention)


def load_camera_config(config_path: str) -> list[ResolvedCamera]:
    raw_cameras = load_camera_inputs(config_path)
    return validate_camera_inputs(raw_cameras)


def load_camera_inputs(config_path: str) -> list[CameraConfigInput]:
    parsed = load_camera_config_file(config_path)
    if config_uses_printer_first(config_path):
        return camera_inputs_from_printers(parsed.printers)
    return parsed.cameras


def load_camera_config_file(config_path: str) -> CameraConfigFile:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        data = {"cameras": data}
    if not isinstance(data, dict):
        raise ValueError("Camera config root must be an object with a 'cameras' array")

    return CameraConfigFile.model_validate(data)


def config_uses_printer_first(config_path: str) -> bool:
    path = Path(config_path)
    if not path.exists():
        return False

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return isinstance(data, dict) and "printers" in data


def camera_inputs_from_printers(printers: list[PrinterConfigInput]) -> list[CameraConfigInput]:
    cameras: list[CameraConfigInput] = []
    seen_camera_ids: set[str] = set()

    for printer in printers:
        default_camera_id = (printer.default_camera_id or "").strip() or None
        for nested_camera in printer.cameras:
            if nested_camera.id in seen_camera_ids:
                raise ValueError(f"Camera ids must be unique: duplicate '{nested_camera.id}'")
            seen_camera_ids.add(nested_camera.id)
            cameras.append(_camera_input_from_printer_camera(printer, nested_camera, default_camera_id))

    return cameras


def _camera_input_from_printer_camera(
    printer: PrinterConfigInput,
    camera: PrinterCameraConfigInput,
    default_camera_id: str | None,
) -> CameraConfigInput:
    return CameraConfigInput(
        id=camera.id,
        name=camera.name,
        enabled=printer.enabled and camera.enabled,
        description=camera.description,
        mode=camera.mode,
        printer_id=printer.id,
        printer_name=printer.name,
        default_live_view=bool(default_camera_id and camera.id == default_camera_id),
        moonraker_url=(printer.moonraker_url or "").strip() or None,
        printer_display_order=printer.display_order,
        display_order=camera.display_order,
        go2rtc_base_url=(camera.go2rtc_base_url or "").strip() or None,
        stream_name=(camera.stream_name or "").strip() or None,
        preview_url=(camera.preview_url or "").strip() or None,
        record_url=(camera.record_url or "").strip() or None,
        gopro_host=(camera.gopro_host or "").strip() or None,
        preview_mode=camera.preview_mode,
        auto_download_after_stop=camera.auto_download_after_stop,
        download_timeout_seconds=camera.download_timeout_seconds,
        file_stabilization_wait_seconds=camera.file_stabilization_wait_seconds,
        output_subdir=(camera.output_subdir or "").strip() or camera.id,
    )


def load_app_settings(config_path: str) -> AppSettingsFile:
    path = Path(config_path)
    if not path.exists():
        return AppSettingsFile()

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("App config root must be an object")

    return AppSettingsFile.model_validate(data)


def _validate_unique_camera_ids(cameras: list[ResolvedCamera]) -> None:
    camera_ids = [camera.id for camera in cameras]
    if len(camera_ids) != len(set(camera_ids)):
        raise ValueError("Camera ids must be unique")


def validate_camera_inputs(cameras: list[CameraConfigInput]) -> list[ResolvedCamera]:
    resolved = [resolve_camera(camera) for camera in cameras]
    _validate_unique_camera_ids(resolved)
    return resolved


def slugify_camera_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "camera"


def build_camera_input(payload: CameraUpsertRequest) -> CameraConfigInput:
    generated_id = slugify_camera_id(payload.name)
    camera_id = (payload.id or generated_id).strip() or generated_id
    printer_id = (payload.printer_id or "").strip() or None
    printer_name = (payload.printer_name or "").strip() or None

    mode: CameraMode = payload.mode
    preview_mode = payload.preview_mode
    preview_url = (payload.preview_url or "").strip() or None
    record_url = (payload.record_url or "").strip() or None
    go2rtc_base_url = (payload.go2rtc_base_url or "").strip() or None
    stream_name = (payload.stream_name or "").strip() or None
    gopro_host = (payload.gopro_host or "").strip() or None

    if mode == "go2rtc_helper":
        preview_url = None
        record_url = None
        gopro_host = None
        preview_mode = None
    elif mode == "manual_urls":
        go2rtc_base_url = None
        stream_name = None
        gopro_host = None
        preview_mode = None
    elif mode == "gopro":
        go2rtc_base_url = None
        stream_name = None
        record_url = None
        preview_mode = preview_mode or "none"
        if preview_mode != "external_link":
            preview_url = None

    return CameraConfigInput(
        id=camera_id,
        name=payload.name.strip(),
        enabled=payload.enabled,
        description=(payload.description or "").strip() or None,
        mode=mode,
        printer_id=printer_id,
        printer_name=printer_name,
        default_live_view=payload.default_live_view,
        moonraker_url=(payload.moonraker_url or "").strip() or None,
        display_order=payload.display_order,
        go2rtc_base_url=go2rtc_base_url,
        stream_name=stream_name,
        preview_url=preview_url,
        record_url=record_url,
        gopro_host=gopro_host,
        preview_mode=preview_mode,
        auto_download_after_stop=payload.auto_download_after_stop,
        download_timeout_seconds=payload.download_timeout_seconds,
        file_stabilization_wait_seconds=payload.file_stabilization_wait_seconds,
        output_subdir=(payload.output_subdir or "").strip() or camera_id,
    )


def write_camera_inputs(
    config_path: str,
    cameras: list[CameraConfigInput],
    *,
    prefer_printer_config: bool = False,
) -> None:
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if prefer_printer_config:
        payload = {
            "printers": [
                printer.model_dump(exclude_none=True)
                for printer in printer_configs_from_camera_inputs(cameras)
            ],
        }
    else:
        payload = {
            "cameras": [camera.model_dump(exclude_none=True) for camera in cameras],
        }

    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def printer_configs_from_camera_inputs(cameras: list[CameraConfigInput]) -> list[PrinterConfigInput]:
    grouped: dict[str, list[CameraConfigInput]] = {}
    order: list[str] = []
    for camera in cameras:
        printer_id = (camera.printer_id or "").strip() or camera.id
        if printer_id not in grouped:
            grouped[printer_id] = []
            order.append(printer_id)
        grouped[printer_id].append(camera)

    printers: list[PrinterConfigInput] = []
    for printer_id in order:
        grouped_cameras = grouped[printer_id]
        sorted_cameras = sorted(grouped_cameras, key=_camera_input_sort_key)
        primary = sorted_cameras[0]
        default_camera = next(
            (camera for camera in sorted_cameras if camera.default_live_view),
            primary,
        )
        printer_name = (primary.printer_name or "").strip() or primary.name
        moonraker_url = _first_non_empty(camera.moonraker_url for camera in sorted_cameras)
        display_order = _first_printer_display_order(sorted_cameras)
        printers.append(
            PrinterConfigInput(
                id=printer_id,
                name=printer_name,
                enabled=any(camera.enabled for camera in sorted_cameras),
                moonraker_url=moonraker_url,
                display_order=display_order,
                default_camera_id=default_camera.id,
                cameras=[
                    printer_camera_config_from_camera_input(camera)
                    for camera in sorted(sorted_cameras, key=_camera_input_sort_key)
                ],
            )
        )

    return sorted(printers, key=_printer_config_sort_key)


def printer_camera_config_from_camera_input(camera: CameraConfigInput) -> PrinterCameraConfigInput:
    mode = infer_input_mode(camera)
    return PrinterCameraConfigInput(
        id=camera.id,
        name=camera.name,
        enabled=camera.enabled,
        description=camera.description,
        mode=mode,
        display_order=camera.display_order,
        go2rtc_base_url=camera.go2rtc_base_url,
        stream_name=camera.stream_name,
        preview_url=camera.preview_url,
        record_url=camera.record_url,
        gopro_host=camera.gopro_host,
        preview_mode=camera.preview_mode,
        auto_download_after_stop=camera.auto_download_after_stop,
        download_timeout_seconds=camera.download_timeout_seconds,
        file_stabilization_wait_seconds=camera.file_stabilization_wait_seconds,
        output_subdir=camera.output_subdir or camera.id,
    )


def _first_non_empty(values) -> str | None:
    for value in values:
        stripped = (value or "").strip()
        if stripped:
            return stripped
    return None


def _first_display_order(cameras: list[CameraConfigInput]) -> int | None:
    orders = [camera.display_order for camera in cameras if camera.display_order is not None]
    return min(orders) if orders else None


def _first_printer_display_order(cameras: list[CameraConfigInput]) -> int | None:
    orders = [
        camera.printer_display_order
        for camera in cameras
        if camera.printer_display_order is not None
    ]
    if orders:
        return min(orders)
    return _first_display_order(cameras)


def _camera_input_sort_key(camera: CameraConfigInput) -> tuple:
    return (
        0 if camera.enabled else 1,
        0 if camera.default_live_view else 1,
        0 if (camera.preview_url or camera.go2rtc_base_url) else 1,
        camera.display_order if camera.display_order is not None else 9999,
        camera.name.lower(),
        camera.id.lower(),
    )


def _printer_config_sort_key(printer: PrinterConfigInput) -> tuple:
    return (
        printer.display_order if printer.display_order is not None else 9999,
        printer.name.lower(),
        printer.id.lower(),
    )


def build_management_items(
    raw_cameras: list[CameraConfigInput],
    resolved_cameras: list[ResolvedCamera],
) -> list[CameraManagementItem]:
    resolved_index = {camera.id: camera for camera in resolved_cameras}
    items: list[CameraManagementItem] = []
    for raw_camera in raw_cameras:
        resolved = resolved_index[raw_camera.id]
        mode = infer_input_mode(raw_camera)
        items.append(
            CameraManagementItem(
                id=raw_camera.id,
                name=raw_camera.name,
                enabled=raw_camera.enabled,
                output_subdir=raw_camera.output_subdir or raw_camera.id,
                description=raw_camera.description,
                mode=mode,
                printer_id=resolved.printer_id,
                printer_name=resolved.printer_name,
                default_live_view=resolved.default_live_view,
                moonraker_url=resolved.moonraker_url,
                display_order=resolved.display_order,
                go2rtc_base_url=raw_camera.go2rtc_base_url,
                stream_name=raw_camera.stream_name,
                preview_url=raw_camera.preview_url,
                record_url=raw_camera.record_url,
                gopro_host=raw_camera.gopro_host,
                preview_mode=_effective_preview_mode(raw_camera.preview_mode)
                if mode == "gopro"
                else None,
                auto_download_after_stop=raw_camera.auto_download_after_stop,
                download_timeout_seconds=raw_camera.download_timeout_seconds,
                file_stabilization_wait_seconds=raw_camera.file_stabilization_wait_seconds,
                resolved_preview_url=resolved.preview_url,
                resolved_record_url=resolved.record_url,
            )
        )
    return items


def _effective_preview_mode(
    value: str | None,
) -> CameraPreviewMode:
    if value == "external_link":
        return "external_link"
    return "none"
