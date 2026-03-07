from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
def get_status(request: Request) -> dict:
    runtime_state = request.app.state.runtime_state
    return {"cameras": runtime_state.as_payload()}
