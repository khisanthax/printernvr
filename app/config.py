from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from app.models import (
    AppConfig,
    AppSettingsFile,
    CameraManagementItem,
    CameraConfigFile,
    CameraConfigInput,
    CameraUpsertRequest,
    ResolvedCamera,
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
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        data = {"cameras": data}
    if not isinstance(data, dict):
        raise ValueError("Camera config root must be an object with a 'cameras' array")

    parsed = CameraConfigFile.model_validate(data)
    return parsed.cameras


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

    return CameraConfigInput(
        id=camera_id,
        name=payload.name.strip(),
        enabled=payload.enabled,
        description=(payload.description or "").strip() or None,
        go2rtc_base_url=(
            payload.go2rtc_base_url.strip() if payload.go2rtc_base_url else None
        ),
        stream_name=(payload.stream_name or "").strip() or None,
        preview_url=(payload.preview_url or "").strip() or None,
        record_url=(payload.record_url or "").strip() or None,
        output_subdir=(payload.output_subdir or "").strip() or camera_id,
    )


def write_camera_inputs(config_path: str, cameras: list[CameraConfigInput]) -> None:
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "cameras": [camera.model_dump(exclude_none=True) for camera in cameras],
    }

    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def build_management_items(
    raw_cameras: list[CameraConfigInput],
    resolved_cameras: list[ResolvedCamera],
) -> list[CameraManagementItem]:
    resolved_index = {camera.id: camera for camera in resolved_cameras}
    items: list[CameraManagementItem] = []
    for raw_camera in raw_cameras:
        resolved = resolved_index[raw_camera.id]
        items.append(
            CameraManagementItem(
                id=raw_camera.id,
                name=raw_camera.name,
                enabled=raw_camera.enabled,
                output_subdir=raw_camera.output_subdir or raw_camera.id,
                description=raw_camera.description,
                mode=(
                    "manual_urls"
                    if (raw_camera.preview_url or raw_camera.record_url)
                    else "go2rtc_helper"
                ),
                go2rtc_base_url=raw_camera.go2rtc_base_url,
                stream_name=raw_camera.stream_name,
                preview_url=raw_camera.preview_url,
                record_url=raw_camera.record_url,
                resolved_preview_url=resolved.preview_url,
                resolved_record_url=resolved.record_url,
            )
        )
    return items
