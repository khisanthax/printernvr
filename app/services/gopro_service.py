from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx

from app.models import (
    GoProMediaItem,
    GoProPreviewResult,
    GoProStatusResult,
    ResolvedCamera,
)

LOGGER = logging.getLogger(__name__)
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".lrv"}


class GoProServiceError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        details: str | None = None,
        http_status: int | None = None,
        command: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.http_status = http_status
        self.command = command


class GoProService:
    def __init__(self, default_timeout_seconds: float = 10.0) -> None:
        self._default_timeout = default_timeout_seconds

    def get_status(self, camera: ResolvedCamera) -> GoProStatusResult:
        payload, status_code, command = self._request_json(camera, "/gp/gpControl/status")
        status = payload.get("status", {}) if isinstance(payload, dict) else {}
        return GoProStatusResult(
            reachable=True,
            host=camera.gopro_host or "",
            message="GoPro reachable",
            http_status=status_code,
            recording=self._extract_recording_flag(status),
            battery=self._extract_battery(status),
            command=command,
            raw_status=status if isinstance(status, dict) else {},
        )

    def test_connection(self, camera: ResolvedCamera) -> GoProStatusResult:
        return self.get_status(camera)

    def start_recording(self, camera: ResolvedCamera) -> GoProStatusResult:
        _payload, status_code, command = self._request_json(
            camera,
            "/gp/gpControl/command/shutter",
            params={"p": 1},
        )
        LOGGER.info("GoPro start recording: camera=%s host=%s", camera.id, camera.gopro_host)
        return GoProStatusResult(
            reachable=True,
            host=camera.gopro_host or "",
            message="GoPro recording started",
            http_status=status_code,
            command=command,
        )

    def stop_recording(self, camera: ResolvedCamera) -> GoProStatusResult:
        _payload, status_code, command = self._request_json(
            camera,
            "/gp/gpControl/command/shutter",
            params={"p": 0},
        )
        LOGGER.info("GoPro stop recording: camera=%s host=%s", camera.id, camera.gopro_host)
        return GoProStatusResult(
            reachable=True,
            host=camera.gopro_host or "",
            message="GoPro recording stopped",
            http_status=status_code,
            command=command,
        )

    def list_media(self, camera: ResolvedCamera) -> list[GoProMediaItem]:
        payload, status_code, command = self._request_json(camera, "/gp/gpMediaList")
        LOGGER.info(
            "GoPro media list fetched: camera=%s host=%s status=%s",
            camera.id,
            camera.gopro_host,
            status_code,
        )
        media_entries = payload.get("media", []) if isinstance(payload, dict) else []
        items: list[GoProMediaItem] = []
        for folder_entry in media_entries:
            folder = str(folder_entry.get("d") or "").strip()
            for file_entry in folder_entry.get("fs", []) or []:
                filename = str(file_entry.get("n") or "").strip()
                if not folder or not filename:
                    continue
                extension = Path(filename).suffix.lower()
                created_timestamp = _parse_timestamp(file_entry)
                items.append(
                    GoProMediaItem(
                        folder=folder,
                        filename=filename,
                        relative_key=f"{folder}/{filename}",
                        created_timestamp=created_timestamp,
                        created_at=datetime.fromtimestamp(created_timestamp)
                        if created_timestamp
                        else None,
                        size_bytes=_parse_int(file_entry.get("s")),
                        download_url=(
                            f"http://{camera.gopro_host}:8080/videos/DCIM/"
                            f"{quote(folder)}/{quote(filename)}"
                        ),
                        is_video=extension in VIDEO_EXTENSIONS,
                    )
                )

        items.sort(
            key=lambda item: (
                item.created_timestamp or 0,
                item.relative_key,
            ),
            reverse=True,
        )
        return items

    def find_latest_video(
        self,
        camera: ResolvedCamera,
        media_items: list[GoProMediaItem],
        previous_media_snapshot: set[str] | None = None,
    ) -> list[GoProMediaItem]:
        video_items = [item for item in media_items if item.is_video]
        if not video_items:
            return []
        if previous_media_snapshot:
            new_items = [
                item for item in video_items if item.relative_key not in previous_media_snapshot
            ]
            if new_items:
                return new_items
        return [video_items[0]]

    def download_media(
        self,
        camera: ResolvedCamera,
        media_item: GoProMediaItem,
        destination_dir: Path,
    ) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        target_path = self._unique_destination_path(destination_dir, media_item.filename)
        temp_path = target_path.with_suffix(f"{target_path.suffix}.part")
        command = f"GET {media_item.download_url}"
        LOGGER.info(
            "GoPro download start: camera=%s host=%s source=%s destination=%s",
            camera.id,
            camera.gopro_host,
            media_item.download_url,
            target_path,
        )
        try:
            if temp_path.exists():
                temp_path.unlink()
            with httpx.Client(timeout=camera.download_timeout_seconds) as client:
                with client.stream("GET", media_item.download_url) as response:
                    if response.status_code >= 400:
                        detail = _response_excerpt(response)
                        raise GoProServiceError(
                            "Failed to download GoPro media",
                            details=detail,
                            http_status=response.status_code,
                            command=command,
                        )
                    with temp_path.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            handle.write(chunk)
            temp_path.replace(target_path)
        except httpx.TimeoutException as exc:
            raise GoProServiceError(
                "GoPro media download timed out",
                details=str(exc),
                command=command,
            ) from exc
        except httpx.HTTPError as exc:
            raise GoProServiceError(
                "GoPro media download failed",
                details=str(exc),
                command=command,
            ) from exc
        except OSError as exc:
            raise GoProServiceError(
                "GoPro media download failed",
                details=str(exc),
                command=command,
            ) from exc
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

        LOGGER.info(
            "GoPro download saved: camera=%s host=%s destination=%s",
            camera.id,
            camera.gopro_host,
            target_path,
        )
        return target_path

    def get_preview_info(self, camera: ResolvedCamera) -> GoProPreviewResult:
        if camera.preview_mode == "external_link" and camera.preview_url:
            return GoProPreviewResult(
                available=True,
                preview_mode="external_link",
                open_url=camera.preview_url,
                message="Open the GoPro preview in a separate tab or device app.",
            )
        return GoProPreviewResult(
            available=False,
            preview_mode=camera.preview_mode or "none",
            message="Preview unavailable in-app for this GoPro configuration.",
        )

    def sleep_for_stabilization(self, camera: ResolvedCamera) -> None:
        wait_seconds = max(camera.file_stabilization_wait_seconds, 0)
        if wait_seconds:
            time.sleep(wait_seconds)

    def _request_json(
        self,
        camera: ResolvedCamera,
        path: str,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> tuple[dict, int, str]:
        host = (camera.gopro_host or "").strip()
        if not host:
            raise GoProServiceError("GoPro host is not configured")
        url = f"http://{host}{path}"
        command = self._build_command(url, params)
        try:
            with httpx.Client(timeout=timeout or self._default_timeout) as client:
                response = client.get(url, params=params)
        except httpx.TimeoutException as exc:
            LOGGER.warning(
                "GoPro request timeout: camera=%s host=%s command=%s error=%s",
                camera.id,
                host,
                command,
                exc,
            )
            raise GoProServiceError(
                "GoPro request timed out",
                details=str(exc),
                command=command,
            ) from exc
        except httpx.HTTPError as exc:
            LOGGER.warning(
                "GoPro request failed: camera=%s host=%s command=%s error=%s",
                camera.id,
                host,
                command,
                exc,
            )
            raise GoProServiceError(
                "GoPro unreachable",
                details=str(exc),
                command=command,
            ) from exc

        if response.status_code >= 400:
            detail = response.text[:400]
            LOGGER.warning(
                "GoPro request error: camera=%s host=%s command=%s status=%s body=%s",
                camera.id,
                host,
                command,
                response.status_code,
                detail,
            )
            raise GoProServiceError(
                "GoPro request failed",
                details=detail,
                http_status=response.status_code,
                command=command,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            detail = response.text[:400]
            LOGGER.warning(
                "GoPro response parse failed: camera=%s host=%s command=%s body=%s",
                camera.id,
                host,
                command,
                detail,
            )
            raise GoProServiceError(
                "GoPro returned invalid JSON",
                details=detail,
                http_status=response.status_code,
                command=command,
            ) from exc

        return payload, response.status_code, command

    def _build_command(self, url: str, params: dict | None) -> str:
        if not params:
            return f"GET {url}"
        query = "&".join(f"{key}={value}" for key, value in params.items())
        return f"GET {url}?{query}"

    def _unique_destination_path(self, destination_dir: Path, filename: str) -> Path:
        safe_name = _sanitize_filename(filename)
        candidate = destination_dir / safe_name
        if not candidate.exists():
            return candidate

        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix
        collision_suffix = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        counter = 1
        while True:
            name = f"{stem}_{collision_suffix}"
            if counter > 1:
                name = f"{name}_{counter}"
            candidate = destination_dir / f"{name}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _extract_recording_flag(self, status: dict) -> bool | None:
        for key in ("8", "10", "13"):
            value = status.get(key)
            if isinstance(value, int):
                return value == 1
        return None

    def _extract_battery(self, status: dict) -> int | None:
        for key in ("2", "70"):
            value = status.get(key)
            if isinstance(value, int):
                return value
        return None


def _sanitize_filename(filename: str) -> str:
    clean = Path(filename).name
    clean = clean.replace("..", "_")
    clean = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in clean)
    clean = clean.strip("._") or "gopro_clip"
    suffix = Path(clean).suffix
    stem = Path(clean).stem or "gopro_clip"
    return f"{stem}{suffix}"


def _parse_timestamp(file_entry: dict) -> int | None:
    for key in ("mod", "cre", "ts"):
        value = _parse_int(file_entry.get(key))
        if value:
            return value
    return None


def _parse_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _response_excerpt(response: httpx.Response) -> str:
    text = response.text[:400]
    if text:
        return text
    return f"HTTP {response.status_code}"
