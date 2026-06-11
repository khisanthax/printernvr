from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from app.models import ClipItem, LatestClipInfo, OUTPUT_SUBDIR_RE, ResolvedCamera

LOGGER = logging.getLogger(__name__)


class ClipStore:
    def __init__(self, recordings_root: str) -> None:
        self._recordings_root = Path(recordings_root)
        self._metadata_filename = ".clip_metadata.json"

    def list_clips(
        self,
        cameras: list[ResolvedCamera],
        active_output_paths: set[str],
        camera_id: str | None = None,
    ) -> list[ClipItem]:
        root = self._recordings_root.resolve(strict=False)
        if not root.exists():
            return []

        known_output_dirs = {camera.output_subdir: camera.id for camera in cameras}
        active_paths = {
            str(Path(path).resolve(strict=False))
            for path in active_output_paths
            if path
        }
        metadata = self._load_metadata()

        clips: list[ClipItem] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.name.endswith(".part"):
                continue
            if path.name == self._metadata_filename:
                continue

            try:
                relative = path.relative_to(root)
            except ValueError:
                continue

            if len(relative.parts) < 2:
                continue
            if relative.parts[0] == "timelapses":
                continue

            storage_dir = relative.parts[0]
            clip_camera_id = known_output_dirs.get(storage_dir) or storage_dir
            if camera_id and clip_camera_id != camera_id:
                continue
            clip_metadata = metadata.get(_metadata_key(clip_camera_id, path.name), {})

            try:
                stat = path.stat()
            except OSError as exc:
                LOGGER.warning("Unable to stat clip %s: %s", path, exc)
                continue

            clips.append(
                ClipItem(
                    camera_id=clip_camera_id,
                    filename=path.name,
                    relative_path=relative.as_posix(),
                    created_at=datetime.fromtimestamp(stat.st_ctime),
                    size_bytes=stat.st_size,
                    size_human=_human_size(stat.st_size),
                    active=str(path.resolve(strict=False)) in active_paths,
                    favorite=bool(clip_metadata.get("favorite")),
                    rejected=bool(clip_metadata.get("rejected")),
                )
            )

        clips.sort(key=lambda item: item.created_at, reverse=True)
        return clips

    def latest_clip(
        self,
        cameras: list[ResolvedCamera],
        active_output_paths: set[str],
        camera_id: str,
    ) -> LatestClipInfo:
        clips = [
            clip
            for clip in self.list_clips(cameras, active_output_paths, camera_id=camera_id)
            if not clip.active
        ]
        if not clips:
            return LatestClipInfo(camera_id=camera_id, has_latest_clip=False)

        latest = clips[0]
        return LatestClipInfo(
            camera_id=latest.camera_id,
            has_latest_clip=True,
            filename=latest.filename,
            created_at=latest.created_at,
            size_bytes=latest.size_bytes,
            size_human=latest.size_human,
            preview_url=_clip_url("preview", latest.camera_id, latest.filename),
            download_url=_clip_url("download", latest.camera_id, latest.filename),
        )

    def resolve_clip_path(
        self,
        camera_id: str,
        filename: str,
        cameras: list[ResolvedCamera],
    ) -> Path:
        storage_dir = self._storage_dir_for_camera(camera_id, cameras)
        return self._resolve_storage_path(storage_dir, filename)

    def delete_clip(
        self,
        camera_id: str,
        filename: str,
        cameras: list[ResolvedCamera],
    ) -> Path:
        clip_path = self.resolve_clip_path(camera_id, filename, cameras)
        if not clip_path.exists() or not clip_path.is_file():
            raise FileNotFoundError(str(clip_path))

        clip_path.unlink()
        LOGGER.info("Deleted clip %s", clip_path)
        self._delete_metadata(camera_id, filename)
        return clip_path

    def update_clip_metadata(
        self,
        camera_id: str,
        filename: str,
        favorite: bool | None = None,
        rejected: bool | None = None,
    ) -> dict:
        metadata = self._load_metadata()
        key = _metadata_key(camera_id, filename)
        entry = dict(metadata.get(key, {}))

        if favorite is not None:
            entry["favorite"] = favorite
        if rejected is not None:
            entry["rejected"] = rejected

        entry["updated_at"] = datetime.now().isoformat()
        metadata[key] = entry
        self._write_metadata(metadata)
        return entry

    def rename_clip(
        self,
        camera_id: str,
        filename: str,
        new_filename: str,
        cameras: list[ResolvedCamera],
    ) -> Path:
        source = self.resolve_clip_path(camera_id, filename, cameras)
        target_name = _normalize_clip_filename(filename, new_filename)
        target = self._resolve_storage_path(source.parent.name, target_name)

        if not source.exists() or not source.is_file():
            raise FileNotFoundError(str(source))
        if target.exists():
            raise FileExistsError(str(target))

        source.rename(target)
        self._rename_metadata(camera_id, filename, target.name)
        LOGGER.info("Renamed clip %s to %s", source, target)
        return target

    def _storage_dir_for_camera(
        self,
        camera_id: str,
        cameras: list[ResolvedCamera],
    ) -> str:
        for camera in cameras:
            if camera.id == camera_id:
                return camera.output_subdir
        return camera_id

    def _resolve_storage_path(self, storage_dir: str, filename: str) -> Path:
        if not OUTPUT_SUBDIR_RE.match(storage_dir) or storage_dir in {".", ".."}:
            raise ValueError("Invalid camera directory")

        clip_name = Path(filename)
        if clip_name.name != filename or filename in {".", ".."}:
            raise ValueError("Invalid filename")

        root = self._recordings_root.resolve(strict=False)
        storage_root = (root / storage_dir).resolve(strict=False)
        clip_path = (storage_root / filename).resolve(strict=False)

        try:
            storage_root.relative_to(root)
            clip_path.relative_to(storage_root)
        except ValueError as exc:
            raise ValueError("Invalid clip path") from exc

        return clip_path

    def _metadata_path(self) -> Path:
        return self._recordings_root.resolve(strict=False) / self._metadata_filename

    def _load_metadata(self) -> dict:
        path = self._metadata_path()
        if not path.exists():
            return {}

        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Unable to read clip metadata %s: %s", path, exc)
            return {}

        return data if isinstance(data, dict) else {}

    def _write_metadata(self, metadata: dict) -> None:
        path = self._metadata_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temp_path.replace(path)

    def _delete_metadata(self, camera_id: str, filename: str) -> None:
        metadata = self._load_metadata()
        key = _metadata_key(camera_id, filename)
        if key not in metadata:
            return
        del metadata[key]
        self._write_metadata(metadata)

    def _rename_metadata(self, camera_id: str, old_filename: str, new_filename: str) -> None:
        metadata = self._load_metadata()
        old_key = _metadata_key(camera_id, old_filename)
        if old_key not in metadata:
            return
        metadata[_metadata_key(camera_id, new_filename)] = metadata.pop(old_key)
        metadata[_metadata_key(camera_id, new_filename)]["updated_at"] = datetime.now().isoformat()
        self._write_metadata(metadata)


def _human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"

    size = float(size_bytes)
    for unit in ["KB", "MB", "GB", "TB"]:
        size /= 1024.0
        if size < 1024.0:
            return f"{size:.2f} {unit}"
    return f"{size:.2f} PB"


def _clip_url(action: str, camera_id: str, filename: str) -> str:
    return (
        f"/api/clips/{action}/"
        f"{quote(camera_id, safe='')}/"
        f"{quote(filename, safe='')}"
    )


def _metadata_key(camera_id: str, filename: str) -> str:
    return f"{camera_id}::{filename}"


def _normalize_clip_filename(original_filename: str, requested_filename: str) -> str:
    normalized = requested_filename.strip()
    if not normalized:
        raise ValueError("Filename cannot be empty")

    clip_name = Path(normalized)
    if clip_name.name != normalized or normalized in {".", ".."}:
        raise ValueError("Invalid filename")
    if normalized.endswith(".part"):
        raise ValueError("Invalid filename")

    requested_suffix = Path(normalized).suffix
    original_suffix = Path(original_filename).suffix
    if requested_suffix:
        if original_suffix and requested_suffix.lower() != original_suffix.lower():
            raise ValueError(f"Filename must keep the {original_suffix} extension")
        return normalized

    return f"{normalized}{original_suffix}" if original_suffix else normalized
