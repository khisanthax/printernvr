from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from app.models import AppConfig, CameraConfigInput, ConfigFile, ResolvedCamera


def generate_go2rtc_urls(go2rtc_base_url: str, stream_name: str | None = None) -> tuple[str, str]:
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


def load_app_config(config_path: str) -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        data = {"cameras": data}
    if not isinstance(data, dict):
        raise ValueError("Config root must be an object with a 'cameras' array")

    parsed = ConfigFile.model_validate(data)

    resolved: list[ResolvedCamera] = [resolve_camera(camera) for camera in parsed.cameras]

    _validate_unique_camera_ids(resolved)

    return AppConfig(cameras=resolved)


def _validate_unique_camera_ids(cameras: list[ResolvedCamera]) -> None:
    camera_ids = [camera.id for camera in cameras]
    if len(camera_ids) != len(set(camera_ids)):
        raise ValueError("Camera ids must be unique")

