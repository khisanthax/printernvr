from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


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
