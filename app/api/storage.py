from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from app.inventory import build_inventory
from app.operations import camera_transaction

router = APIRouter(prefix="/api/storage", tags=["storage"])


@router.get("/inventory")
def get_inventory(request: Request) -> dict:
    state = request.app.state
    return build_inventory(
        Path(state.settings["recordings_dir"]), state.clip_store, state.cameras,
        state.runtime_state.active_output_paths(),
    )


@router.get("/status")
def get_storage_status(request: Request) -> dict:
    retention_manager = request.app.state.retention_manager
    runtime_state = request.app.state.runtime_state
    timelapse_manager = request.app.state.timelapse_manager
    active_paths = runtime_state.active_output_paths() | timelapse_manager.active_paths() | request.app.state.optimizer.active_paths()
    status = retention_manager.get_storage_status(active_paths)
    return status.model_dump(mode="json")


@router.get("/cleanup/preview")
def preview_storage_cleanup(request: Request) -> dict:
    state = request.app.state
    active_paths = state.runtime_state.active_output_paths() | state.timelapse_manager.active_paths() | state.optimizer.active_paths()
    return state.retention_manager.preview(active_paths)


@router.post("/cleanup", dependencies=[Depends(camera_transaction)])
def run_storage_cleanup(request: Request, confirm: bool = False) -> dict:
    if not confirm:
        raise HTTPException(status_code=400, detail="Review the cleanup preview and confirm deletion")
    retention_manager = request.app.state.retention_manager
    runtime_state = request.app.state.runtime_state
    timelapse_manager = request.app.state.timelapse_manager
    active_paths = runtime_state.active_output_paths() | timelapse_manager.active_paths() | request.app.state.optimizer.active_paths()

    try:
        summary = retention_manager.enforce_retention(
            active_paths,
            triggered_by="manual_cleanup",
            manual=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    status = retention_manager.get_storage_status(active_paths)
    return {
        "summary": summary.model_dump(mode="json") if summary else None,
        "status": status.model_dump(mode="json"),
    }
