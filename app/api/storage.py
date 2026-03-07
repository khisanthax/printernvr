from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/storage", tags=["storage"])


@router.get("/status")
def get_storage_status(request: Request) -> dict:
    retention_manager = request.app.state.retention_manager
    runtime_state = request.app.state.runtime_state
    status = retention_manager.get_storage_status(runtime_state.active_output_paths())
    return status.model_dump(mode="json")


@router.post("/cleanup")
def run_storage_cleanup(request: Request) -> dict:
    retention_manager = request.app.state.retention_manager
    runtime_state = request.app.state.runtime_state

    try:
        summary = retention_manager.enforce_retention(
            runtime_state.active_output_paths(),
            triggered_by="manual_cleanup",
            manual=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    status = retention_manager.get_storage_status(runtime_state.active_output_paths())
    return {
        "summary": summary.model_dump(mode="json") if summary else None,
        "status": status.model_dump(mode="json"),
    }
