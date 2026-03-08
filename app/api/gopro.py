from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.config import build_camera_input, resolve_camera
from app.models import CameraUpsertRequest, RecordStartRequest
from app.services.gopro_service import GoProServiceError

router = APIRouter(prefix="/api/gopro", tags=["gopro"])


@router.post("/test")
def test_gopro(payload: CameraUpsertRequest, request: Request) -> dict:
    camera = _resolve_draft_gopro(payload)
    service = request.app.state.gopro_service
    try:
        result = service.test_connection(camera)
    except GoProServiceError as exc:
        raise HTTPException(
            status_code=502,
            detail=exc.message if not exc.details else f"{exc.message}: {exc.details}",
        ) from exc
    return result.model_dump(mode="json")


@router.get("/{camera_id}/status")
def gopro_status(camera_id: str, request: Request) -> dict:
    camera = _require_gopro_camera(camera_id, request)
    manager = request.app.state.gopro_recording_manager
    try:
        result = manager.get_status(camera)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GoProServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.post("/{camera_id}/record_for")
def gopro_record_for(
    camera_id: str,
    request: Request,
    payload: RecordStartRequest | None = None,
) -> dict:
    camera = _require_gopro_camera(camera_id, request)
    manager = request.app.state.gopro_recording_manager
    seconds = (payload.duration if payload else None) or 30
    if seconds < 1:
        raise HTTPException(status_code=400, detail="duration must be greater than zero")
    try:
        state = manager.record_for(camera, seconds)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"camera": state.model_dump(mode="json")}


@router.post("/{camera_id}/download_latest")
def gopro_download_latest(camera_id: str, request: Request) -> dict:
    camera = _require_gopro_camera(camera_id, request)
    manager = request.app.state.gopro_recording_manager
    try:
        result = manager.download_latest(camera)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.get("/{camera_id}/preview")
def gopro_preview(camera_id: str, request: Request) -> dict:
    camera = _require_gopro_camera(camera_id, request)
    manager = request.app.state.gopro_recording_manager
    result = manager.get_preview_info(camera)
    return result.model_dump(mode="json")


@router.get("/{camera_id}/media")
def gopro_media(camera_id: str, request: Request) -> dict:
    camera = _require_gopro_camera(camera_id, request)
    manager = request.app.state.gopro_recording_manager
    try:
        items = manager.list_media(camera)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GoProServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"media": [item.model_dump(mode="json") for item in items]}


def _resolve_draft_gopro(payload: CameraUpsertRequest):
    try:
        camera_input = build_camera_input(payload)
        resolved = resolve_camera(camera_input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if resolved.mode != "gopro":
        raise HTTPException(status_code=400, detail="Draft camera is not in gopro mode")
    return resolved


def _require_gopro_camera(camera_id: str, request: Request):
    camera = request.app.state.camera_index.get(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Unknown camera '{camera_id}'")
    if camera.mode != "gopro":
        raise HTTPException(status_code=400, detail=f"Camera '{camera_id}' is not a GoPro")
    return camera
