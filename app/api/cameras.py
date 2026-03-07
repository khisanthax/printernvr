from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["cameras"])


@router.get("/cameras")
def get_cameras(request: Request) -> dict:
    cameras = request.app.state.cameras
    return {"cameras": [camera.model_dump() for camera in cameras]}
