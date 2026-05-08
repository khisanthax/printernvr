from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.models import ClipItem, ClipMetadataUpdate, ClipRenameRequest

router = APIRouter(prefix="/api/clips", tags=["clips"])


@router.get("")
def get_clips(
    request: Request,
    camera_id: str | None = Query(default=None),
    review_status: str = Query(default="all"),
    q: str | None = Query(default=None),
) -> dict:
    clip_store = request.app.state.clip_store
    runtime_state = request.app.state.runtime_state
    cameras = request.app.state.cameras

    clips = clip_store.list_clips(
        cameras=cameras,
        active_output_paths=runtime_state.active_output_paths(),
        camera_id=camera_id,
    )
    clips = _filter_clips(clips, review_status=review_status, query=q)
    return {"clips": [clip.model_dump(mode="json") for clip in clips]}


@router.get("/latest/{camera_id}")
def get_latest_clip(camera_id: str, request: Request) -> dict:
    clip_store = request.app.state.clip_store
    runtime_state = request.app.state.runtime_state
    cameras = request.app.state.cameras
    camera_index = request.app.state.camera_index

    if camera_id not in camera_index:
        raise HTTPException(status_code=404, detail=f"Unknown camera '{camera_id}'")

    latest = clip_store.latest_clip(
        cameras=cameras,
        active_output_paths=runtime_state.active_output_paths(),
        camera_id=camera_id,
    )
    return latest.model_dump(mode="json")


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


@router.patch("/{camera_id}/{filename}/metadata")
def update_clip_metadata(
    camera_id: str,
    filename: str,
    payload: ClipMetadataUpdate,
    request: Request,
) -> dict:
    clip_store = request.app.state.clip_store
    cameras = request.app.state.cameras

    _resolve_clip_path(camera_id, filename, request)
    metadata = clip_store.update_clip_metadata(
        camera_id=camera_id,
        filename=filename,
        favorite=payload.favorite,
        rejected=payload.rejected,
    )
    return {
        "camera_id": camera_id,
        "filename": filename,
        "favorite": bool(metadata.get("favorite")),
        "rejected": bool(metadata.get("rejected")),
        "clips": [
            clip.model_dump(mode="json")
            for clip in clip_store.list_clips(
                cameras=cameras,
                active_output_paths=request.app.state.runtime_state.active_output_paths(),
                camera_id=camera_id,
            )
            if clip.filename == filename
        ],
    }


@router.post("/{camera_id}/{filename}/rename")
def rename_clip(
    camera_id: str,
    filename: str,
    payload: ClipRenameRequest,
    request: Request,
) -> dict:
    clip_store = request.app.state.clip_store
    cameras = request.app.state.cameras
    runtime_state = request.app.state.runtime_state

    clip_path = _resolve_clip_path(camera_id, filename, request)
    _raise_if_active(clip_path, runtime_state.active_output_paths())

    try:
        renamed_path = clip_store.rename_clip(camera_id, filename, payload.filename, cameras)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Clip not found") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="A clip with that filename already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to rename clip: {exc}") from exc

    return {
        "renamed": True,
        "camera_id": camera_id,
        "old_filename": filename,
        "filename": renamed_path.name,
    }


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
    _raise_if_active(clip_path, active_paths)

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


def _raise_if_active(clip_path: Path, active_paths: set[str]) -> None:
    normalized_path = str(clip_path.resolve(strict=False))
    if normalized_path in {str(Path(path).resolve(strict=False)) for path in active_paths if path}:
        raise HTTPException(
            status_code=409,
            detail="Active recording files cannot be modified",
        )


def _filter_clips(clips: list[ClipItem], review_status: str, query: str | None) -> list[ClipItem]:
    normalized_status = review_status.lower().strip()
    if normalized_status not in {"all", "favorites", "rejected", "kept"}:
        raise HTTPException(status_code=400, detail="Invalid review_status filter")

    if normalized_status == "favorites":
        clips = [clip for clip in clips if clip.favorite]
    elif normalized_status == "rejected":
        clips = [clip for clip in clips if clip.rejected]
    elif normalized_status == "kept":
        clips = [clip for clip in clips if not clip.rejected]

    normalized_query = (query or "").strip().lower()
    if normalized_query:
        clips = [
            clip
            for clip in clips
            if normalized_query in clip.filename.lower()
            or normalized_query in clip.camera_id.lower()
            or normalized_query in clip.relative_path.lower()
        ]

    return clips
