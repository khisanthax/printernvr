from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import disk_usage, which
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/ready")
def readiness(request: Request) -> JSONResponse:
    state = request.app.state
    tools_ready = bool(which("ffmpeg") and which("ffprobe"))
    storage_ready = False
    if getattr(state, "settings", None):
        root = Path(state.settings["recordings_dir"])
        try:
            with NamedTemporaryFile(dir=root):
                reserve = state.app_config.retention.capture_reserve_mib * 1024**2
                storage_ready = disk_usage(root).free >= reserve
        except OSError:
            pass
    ready = tools_ready and storage_ready
    return JSONResponse(
        {"ready": ready, "media_tools": tools_ready, "recording_storage": storage_ready},
        status_code=200 if ready else 503,
    )


@router.get("/health")
def health(request: Request) -> dict:
    cameras = getattr(request.app.state, "cameras", [])
    runtime_state = getattr(request.app.state, "runtime_state", None)
    active_recordings = 0
    if runtime_state is not None:
        active_recordings = sum(1 for state in runtime_state.list_states() if state.recording)
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera_count": len(cameras),
        "active_recordings": active_recordings,
    }
