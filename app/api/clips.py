from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/clips", tags=["clips"])


@router.get("")
def get_clips(
    request: Request,
    camera_id: str | None = Query(default=None),
) -> dict:
    clip_store = request.app.state.clip_store
    runtime_state = request.app.state.runtime_state
    cameras = request.app.state.cameras

    clips = clip_store.list_clips(
        cameras=cameras,
        active_output_paths=runtime_state.active_output_paths(),
        camera_id=camera_id,
    )
    return {"clips": [clip.model_dump(mode="json") for clip in clips]}


@router.get("/download/{camera_id}/{filename}")
def download_clip(camera_id: str, filename: str, request: Request) -> FileResponse:
    clip_path = _resolve_clip_path(camera_id, filename, request)
    return FileResponse(
        path=clip_path,
        filename=clip_path.name,
        media_type=_guess_media_type(clip_path),
    )


@router.get("/preview/{camera_id}/{filename}")
def preview_clip(camera_id: str, filename: str, request: Request) -> FileResponse:
    clip_path = _resolve_clip_path(camera_id, filename, request)
    return FileResponse(path=clip_path, media_type=_guess_media_type(clip_path))


def _resolve_clip_path(camera_id: str, filename: str, request: Request) -> Path:
    clip_store = request.app.state.clip_store
    cameras = request.app.state.cameras

    try:
        clip_path = clip_store.resolve_clip_path(camera_id, filename, cameras)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not clip_path.exists() or not clip_path.is_file():
        raise HTTPException(status_code=404, detail="Clip not found")

    return clip_path


@router.delete("/{camera_id}/{filename}")
def delete_clip(camera_id: str, filename: str, request: Request) -> dict:
    clip_store = request.app.state.clip_store
    cameras = request.app.state.cameras
    runtime_state = request.app.state.runtime_state

    try:
        clip_path = clip_store.resolve_clip_path(camera_id, filename, cameras)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    active_paths = runtime_state.active_output_paths()
    normalized_path = str(clip_path.resolve(strict=False))
    if normalized_path in {str(Path(path).resolve(strict=False)) for path in active_paths if path}:
        raise HTTPException(
            status_code=409,
            detail="Active recording files cannot be deleted",
        )

    try:
        deleted_path = clip_store.delete_clip(camera_id, filename, cameras)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Clip not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to delete clip: {exc}") from exc

    return {
        "deleted": True,
        "camera_id": camera_id,
        "filename": filename,
        "relative_path": deleted_path.relative_to(
            Path(request.app.state.settings["recordings_dir"]).resolve(strict=False)
        ).as_posix(),
    }


def _guess_media_type(clip_path: Path) -> str:
    media_type, _encoding = mimetypes.guess_type(clip_path.name)
    return media_type or "application/octet-stream"
