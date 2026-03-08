from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from app.config import build_camera_input, resolve_camera
from app.models import CameraUpsertRequest
from app.probe import probe_record_stream
from app.util import ensure_directories

router = APIRouter(prefix="/api", tags=["cameras"])


@router.get("/cameras")
def get_cameras(request: Request) -> dict:
    camera_store = request.app.state.camera_store
    _raw_cameras, _resolved_cameras, items = camera_store.list_cameras()
    return {"cameras": [item.model_dump() for item in items]}


@router.post("/cameras")
def create_camera(payload: CameraUpsertRequest, request: Request) -> dict:
    camera_store = request.app.state.camera_store

    try:
        _raw_cameras, resolved_cameras, items = camera_store.create_camera(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _refresh_runtime_camera_state(request, resolved_cameras)
    return {"cameras": [item.model_dump() for item in items]}


@router.put("/cameras/{camera_id}")
def update_camera(camera_id: str, payload: CameraUpsertRequest, request: Request) -> dict:
    recorder = request.app.state.recording_manager
    gopro_recorder = request.app.state.gopro_recording_manager
    if recorder.is_recording(camera_id) or gopro_recorder.is_busy(camera_id):
        raise HTTPException(
            status_code=409,
            detail=f"Camera '{camera_id}' is actively recording and cannot be edited",
        )

    camera_store = request.app.state.camera_store
    try:
        _raw_cameras, resolved_cameras, items = camera_store.update_camera(camera_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _refresh_runtime_camera_state(request, resolved_cameras)
    return {"cameras": [item.model_dump() for item in items]}


@router.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str, request: Request) -> dict:
    recorder = request.app.state.recording_manager
    gopro_recorder = request.app.state.gopro_recording_manager
    if recorder.is_recording(camera_id) or gopro_recorder.is_busy(camera_id):
        raise HTTPException(
            status_code=409,
            detail=f"Camera '{camera_id}' is actively recording and must be stopped before deletion",
        )

    camera_store = request.app.state.camera_store
    try:
        _raw_cameras, resolved_cameras, items = camera_store.delete_camera(camera_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _refresh_runtime_camera_state(request, resolved_cameras)
    return {"cameras": [item.model_dump() for item in items]}


@router.post("/camera/probe")
def probe_camera(payload: CameraUpsertRequest) -> dict:
    try:
        camera_input = build_camera_input(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        resolved = resolve_camera(camera_input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if resolved.backend_type != "ffmpeg" or not resolved.record_url:
        raise HTTPException(
            status_code=400,
            detail="Stream probe is only available for ffmpeg/RTSP camera modes",
        )

    result = probe_record_stream(resolved.record_url)
    return result.model_dump(mode="json")


def _refresh_runtime_camera_state(request: Request, resolved_cameras: list) -> None:
    request.app.state.cameras = resolved_cameras
    request.app.state.camera_index = {camera.id: camera for camera in resolved_cameras}
    request.app.state.runtime_state.sync_cameras(resolved_cameras)

    output_dirs = [
        os.path.join(request.app.state.settings["recordings_dir"], camera.output_subdir)
        for camera in resolved_cameras
        if camera.enabled
    ]
    ensure_directories(output_dirs)
