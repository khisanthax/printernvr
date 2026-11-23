from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import AwareDatetime, BaseModel, Field
from starlette.background import BackgroundTask

from app.api.clips import _raise_if_active, _resolve_clip_path
from app.media import validate_mp4
from app.operations import camera_transaction
from app.timeline import EventInput, extract_segment

router = APIRouter()


class ClipRange(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)


class Calibration(BaseModel):
    frame_zero_at: AwareDatetime
    correction_seconds: float = Field(ge=-86400, le=86400, allow_inf_nan=False)


class CalibrationUpdate(BaseModel):
    calibration: Calibration | None


def _printer(state, printer_id):
    cameras = [camera for camera in state.cameras if camera.printer_id == printer_id]
    if not cameras and not any(printer.id == printer_id for printer in state.printers):
        raise HTTPException(status_code=404, detail="Unknown printer")
    return cameras


@router.get("/timeline")
def timeline_page(request: Request):
    printers = {camera.printer_id: camera.printer_name for camera in request.app.state.cameras}
    printers.update({printer.id: printer.name for printer in request.app.state.printers})
    return request.app.state.templates.TemplateResponse(
        request=request, name="timeline.html", context={"printers": sorted(printers.items())},
    )


@router.get("/api/timeline/{printer_id}")
def read_timeline(printer_id: str, request: Request, since: datetime | None = None):
    state = request.app.state
    cameras = _printer(state, printer_id)
    active = state.runtime_state.active_output_paths()
    clips = [clip for camera in cameras for clip in state.clip_store.list_clips(state.cameras, active, camera.id)
             if not clip.active and Path(clip.filename).suffix.lower() == ".mp4"]
    events = state.timeline.events(printer_id)
    if since is not None:
        if since.tzinfo is None:
            raise HTTPException(status_code=422, detail="since must include a timezone")
        events = [event for event in events if datetime.fromisoformat(event["received_at"]) >= since]
    return {"events": events, "clips": [
        {"camera_id": clip.camera_id, "filename": clip.filename,
         "preview_url": f"/api/clips/preview/{quote(clip.camera_id, safe='')}/{quote(clip.filename, safe='')}"}
        for clip in sorted(clips, key=lambda clip: clip.created_at, reverse=True)[:250]
    ]}


@router.post("/api/timeline/{printer_id}/events", status_code=201)
def append_event(printer_id: str, event: EventInput, request: Request):
    state = request.app.state
    _printer(state, printer_id)
    return state.timeline.append(printer_id, event, "submitted")


@router.get("/api/timeline/video/{camera_id}/{filename}")
def video_metadata(camera_id: str, filename: str, request: Request):
    source = _resolve_clip_path(camera_id, filename, request)
    state = request.app.state
    _raise_if_active(source, state.runtime_state.active_output_paths())
    try:
        metadata = validate_mp4(source)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail="This clip cannot be verified as MP4") from exc
    anchor = state.clip_store.recording_anchor(camera_id, filename)
    return {
        "duration": float(metadata["format"]["duration"]),
        "anchor": anchor,
        "calibration": state.clip_store.timeline_calibration(camera_id, filename),
    }


@router.put("/api/timeline/video/{camera_id}/{filename}/calibration", dependencies=[Depends(camera_transaction)])
def update_calibration(camera_id: str, filename: str, payload: CalibrationUpdate, request: Request):
    source = _resolve_clip_path(camera_id, filename, request)
    if source.suffix.lower() != ".mp4":
        raise HTTPException(status_code=422, detail="Timeline calibration is only supported for MP4")
    state = request.app.state
    _raise_if_active(source, state.runtime_state.active_output_paths() | state.optimizer.active_paths())
    value = payload.calibration.model_dump(mode="json") if payload.calibration else None
    try:
        state.clip_store.save_timeline_calibration(camera_id, filename, value)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Could not update clip alignment metadata") from exc
    return {"calibration": value}


@router.post("/api/timeline/video/{camera_id}/{filename}/extract", dependencies=[Depends(camera_transaction)])
def extract_clip(camera_id: str, filename: str, selection: ClipRange, request: Request):
    state = request.app.state
    source = _resolve_clip_path(camera_id, filename, request)
    _raise_if_active(source, state.runtime_state.active_output_paths() | state.optimizer.active_paths())
    if state.runtime_state.active_output_paths() or state.timelapse_manager.active_paths():
        raise HTTPException(status_code=409, detail="Wait for active captures before extracting video")
    directory = TemporaryDirectory(prefix=".timeline-export-", dir=state.settings["recordings_dir"])
    output = Path(directory.name).resolve() / "segment.mp4"
    try:
        reserve = state.app_config.retention.capture_reserve_mib * 1024**2
        extract_segment(source, output, selection.start, selection.end, reserve)
    except (OSError, ValueError) as exc:
        directory.cleanup()
        raise HTTPException(status_code=422, detail="Clip extraction failed" if isinstance(exc, OSError) else str(exc)) from exc
    return FileResponse(output, media_type="video/mp4", filename="timeline-segment.mp4",
                        background=BackgroundTask(directory.cleanup))
