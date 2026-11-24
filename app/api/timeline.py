import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import AwareDatetime, BaseModel, Field
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.api.clips import _raise_if_active, _resolve_clip_path
from app.media import validate_mp4
from app.operations import camera_lock, camera_transaction
from app.timeline import MAX_IMPORT_BYTES, EventInput, export_captions, extract_segment

router = APIRouter()
export_slot = BoundedSemaphore(1)


class Calibration(BaseModel):
    frame_zero_at: AwareDatetime
    correction_seconds: float = Field(ge=-86400, le=86400, allow_inf_nan=False)


class ClipRange(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    timestamped: bool = False
    clock: Literal["source", "received"] = "source"
    alignment: Calibration | None = None


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
    clips = []
    for camera in cameras:
        completed = [clip for clip in state.clip_store.list_clips(state.cameras, active, camera.id)
                     if not clip.active and Path(clip.filename).suffix.lower() == ".mp4"]
        clips.extend(completed[:250])
    events = state.timeline.events(printer_id)
    if since is not None:
        if since.tzinfo is None:
            raise HTTPException(status_code=422, detail="since must include a timezone")
        events = [event for event in events if datetime.fromisoformat(event["received_at"]) >= since]
    timings = state.clip_store.timeline_timings()
    return {"events": events, "cameras": [{"id": camera.id, "name": camera.name} for camera in cameras], "clips": [
        {"camera_id": clip.camera_id, "filename": clip.filename,
         "timing": timings.get((clip.camera_id, clip.filename)),
         "preview_url": f"/api/clips/preview/{quote(clip.camera_id, safe='')}/{quote(clip.filename, safe='')}"}
        for clip in sorted(clips, key=lambda clip: clip.created_at, reverse=True)
    ]}


@router.post("/api/timeline/{printer_id}/events", status_code=201)
def append_event(printer_id: str, event: EventInput, request: Request):
    state = request.app.state
    _printer(state, printer_id)
    return state.timeline.append(printer_id, event, "submitted")


@router.post("/api/timeline/{printer_id}/klipper-log")
async def import_klipper_log(printer_id: str, request: Request):
    state = request.app.state
    _printer(state, printer_id)
    if request.headers.get("content-type", "").split(";", 1)[0] != "text/plain":
        raise HTTPException(status_code=415, detail="Send a plain-text Klipper log")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_IMPORT_BYTES:
            raise HTTPException(status_code=413, detail="Log excerpts are limited to 2 MiB")
        body.extend(chunk)
    try:
        return await run_in_threadpool(state.timeline.import_klipper, printer_id, body.decode("utf-8-sig"))
    except UnicodeError as exc:
        raise HTTPException(status_code=422, detail="The log must contain UTF-8 text") from exc


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


@router.post("/api/timeline/video/{camera_id}/{filename}/extract")
def extract_clip(camera_id: str, filename: str, selection: ClipRange, request: Request):
    state = request.app.state
    if not export_slot.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Another timeline export is running")
    directory = None
    source_handle = None
    download_name = "timeline-segment.mp4"
    try:
        reserve = state.app_config.retention.capture_reserve_mib * 1024**2
        with camera_lock:
            source = _resolve_clip_path(camera_id, filename, request)
            active = state.runtime_state.active_output_paths()
            _raise_if_active(source, active | state.optimizer.active_paths())
            if active or state.timelapse_manager.active_paths():
                raise HTTPException(status_code=409, detail="Wait for active captures before extracting video")
            if not 0 <= selection.start < selection.end <= selection.start + 120:
                raise ValueError("Choose a positive range of up to 120 seconds")
            directory = TemporaryDirectory(prefix=".timeline-export-", dir=state.settings["recordings_dir"])
            folder = Path(directory.name).resolve()
            snapshot = folder / "source.mp4"
            # Pin the current inode, not its public filename, so rename/cleanup can proceed during encoding.
            try:
                os.link(source, snapshot)
            except OSError:
                source_handle = source.open("rb")
            if selection.timestamped:
                camera = next((camera for camera in state.cameras if camera.id == camera_id), None)
                timing = (selection.alignment.model_dump(mode="json") if selection.alignment is not None else
                          state.clip_store.timeline_calibration(camera_id, filename)
                          or state.clip_store.recording_anchor(camera_id, filename))
                if not timing or not camera:
                    raise ValueError("Set a valid clip alignment before exporting timestamps")
                anchor = datetime.fromisoformat(timing["frame_zero_at"]).astimezone(timezone.utc)
                zero = anchor - timedelta(seconds=timing.get("correction_seconds", 0))
        if source_handle is not None:
            if shutil.disk_usage(folder).free < reserve + 128 * 1024**2 + os.fstat(source_handle.fileno()).st_size:
                raise ValueError("Insufficient space to snapshot the source on this volume")
            with source_handle, snapshot.open("xb") as target:
                shutil.copyfileobj(source_handle, target)
        output = folder / "segment.mp4"
        if selection.timestamped:
            export_captions(folder / "timestamps.srt", state.timeline.events(camera.printer_id),
                            zero, selection.start, selection.end, selection.clock)
            stamp = (zero + timedelta(seconds=selection.start)).strftime("%Y%m%dT%H%M%SZ")
            download_name = f"timeline-{stamp}.mp4"
        extract_segment(snapshot, output, selection.start, selection.end, reserve, burn_timestamps=selection.timestamped)
    except (OSError, ValueError, OverflowError) as exc:
        if directory:
            directory.cleanup()
        raise HTTPException(status_code=422, detail="Clip extraction failed" if isinstance(exc, OSError) else str(exc)) from exc
    except Exception:
        if directory:
            directory.cleanup()
        raise
    finally:
        if source_handle is not None:
            source_handle.close()
        export_slot.release()
    return FileResponse(output, media_type="video/mp4", filename=download_name,
                        background=BackgroundTask(directory.cleanup))
