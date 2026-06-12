from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.models import ResolvedCamera, TimelapseStartRequest

router = APIRouter(prefix="/api/timelapse", tags=["timelapse"])


@router.get("/status")
def get_timelapse_status(request: Request) -> dict:
    manager = request.app.state.timelapse_manager
    return {"printers": manager.as_payload()}


@router.get("/outputs")
def get_timelapse_outputs(request: Request) -> dict:
    manager = request.app.state.timelapse_manager
    return {"timelapses": manager.list_outputs()}


@router.post("/start/{printer_id}")
def start_timelapse(
    printer_id: str,
    request: Request,
    payload: TimelapseStartRequest | None = None,
) -> dict:
    payload = payload or TimelapseStartRequest()
    manager = request.app.state.timelapse_manager
    cameras = request.app.state.cameras

    printer_cameras = [camera for camera in cameras if camera.printer_id == printer_id]
    if not printer_cameras:
        raise HTTPException(status_code=404, detail=f"Unknown printer '{printer_id}'")

    camera = _resolve_timelapse_camera(printer_cameras, payload.camera_id)
    if payload.camera_id and not camera:
        raise HTTPException(
            status_code=404,
            detail=f"Camera '{payload.camera_id}' does not belong to printer '{printer_id}'",
        )
    if not camera:
        raise HTTPException(status_code=400, detail=f"Printer '{printer_id}' has no usable camera")

    if camera.backend_type != "ffmpeg" or not camera.record_url:
        raise HTTPException(
            status_code=400,
            detail=f"Camera '{camera.id}' does not have a usable RTSP/recording URL",
        )

    moonraker_url = camera.moonraker_url or _first_moonraker_url(printer_cameras)

    try:
        state = manager.start_session(
            printer_id=printer_id,
            printer_name=camera.printer_name,
            camera=camera,
            interval_seconds=payload.interval_seconds,
            moonraker_url=moonraker_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {"timelapse": state.model_dump(mode="json")}


@router.post("/stop/{printer_id}")
def stop_timelapse(printer_id: str, request: Request) -> dict:
    manager = request.app.state.timelapse_manager
    state = manager.stop_session(printer_id, reason="manual")
    return {"timelapse": state.model_dump(mode="json")}


@router.get("/download/{printer_id}/{session_id}/{filename}")
def download_timelapse(
    printer_id: str,
    session_id: str,
    filename: str,
    request: Request,
) -> FileResponse:
    manager = request.app.state.timelapse_manager
    try:
        output_path = manager.resolve_output_path(printer_id, session_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not output_path.exists() or not output_path.is_file():
        raise HTTPException(status_code=404, detail="Timelapse output not found")

    return FileResponse(
        path=output_path,
        filename=output_path.name,
        media_type=_guess_media_type(output_path),
    )


@router.get("/preview/{printer_id}/{session_id}/{filename}")
def preview_timelapse(
    printer_id: str,
    session_id: str,
    filename: str,
    request: Request,
) -> FileResponse:
    manager = request.app.state.timelapse_manager
    try:
        output_path = manager.resolve_output_path(printer_id, session_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not output_path.exists() or not output_path.is_file():
        raise HTTPException(status_code=404, detail="Timelapse output not found")

    return FileResponse(path=output_path, media_type=_guess_media_type(output_path))


@router.delete("/{printer_id}/{session_id}/{filename}")
def delete_timelapse(
    printer_id: str,
    session_id: str,
    filename: str,
    request: Request,
) -> dict:
    manager = request.app.state.timelapse_manager
    try:
        deleted_path = manager.delete_output(printer_id, session_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Timelapse output not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to delete timelapse: {exc}") from exc

    return {
        "deleted": True,
        "printer_id": printer_id,
        "session_id": session_id,
        "filename": filename,
        "relative_path": deleted_path.relative_to(
            Path(request.app.state.settings["recordings_dir"]).resolve(strict=False)
        ).as_posix(),
    }


def _resolve_timelapse_camera(
    cameras: list[ResolvedCamera],
    camera_id: str | None,
) -> ResolvedCamera | None:
    if camera_id:
        return next((camera for camera in cameras if camera.id == camera_id), None)

    candidates = [
        camera
        for camera in sorted(cameras, key=_camera_sort_key)
        if camera.enabled and camera.backend_type == "ffmpeg" and camera.record_url
    ]
    return candidates[0] if candidates else None


def _camera_sort_key(camera: ResolvedCamera) -> tuple:
    return (
        0 if camera.enabled else 1,
        0 if camera.default_live_view else 1,
        0 if camera.preview_url else 1,
        camera.display_order if camera.display_order is not None else 9999,
        camera.name.lower(),
        camera.id.lower(),
    )


def _first_moonraker_url(cameras: list[ResolvedCamera]) -> str | None:
    for camera in sorted(cameras, key=_camera_sort_key):
        if camera.moonraker_url:
            return camera.moonraker_url
    return None


def _guess_media_type(path: Path) -> str:
    media_type, _encoding = mimetypes.guess_type(path.name)
    return media_type or "application/octet-stream"
