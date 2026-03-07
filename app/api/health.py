from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    cameras = getattr(request.app.state, "cameras", [])
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera_count": len(cameras),
    }
