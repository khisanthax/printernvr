from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models import RecordStartRequest

router = APIRouter(prefix="/api/record", tags=["record"])


@router.get("/status")
def get_record_status(request: Request) -> dict:
    runtime_state = request.app.state.runtime_state
    return {"cameras": runtime_state.as_payload()}


@router.post("/start/{camera_id}")
def start_recording(
    camera_id: str,
    request: Request,
    payload: RecordStartRequest | None = None,
) -> dict:
    camera_index = request.app.state.camera_index
    recorder = request.app.state.recording_manager
    gopro_recorder = request.app.state.gopro_recording_manager

    camera = camera_index.get(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Unknown camera '{camera_id}'")

    try:
        duration = payload.duration if payload else None
        if camera.backend_type == "gopro":
            if duration is not None:
                state = gopro_recorder.record_for(camera, duration)
            else:
                state = gopro_recorder.start_recording(camera)
        else:
            state = recorder.start_recording(camera, duration=duration)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"camera": state.model_dump(mode="json")}


@router.post("/stop/{camera_id}")
def stop_recording(camera_id: str, request: Request) -> dict:
    camera_index = request.app.state.camera_index
    recorder = request.app.state.recording_manager
    gopro_recorder = request.app.state.gopro_recording_manager

    if camera_id not in camera_index:
        raise HTTPException(status_code=404, detail=f"Unknown camera '{camera_id}'")

    camera = camera_index[camera_id]
    try:
        if camera.backend_type == "gopro":
            state = gopro_recorder.stop_recording(camera_id)
        else:
            state = recorder.stop_recording(camera_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {"camera": state.model_dump(mode="json")}
