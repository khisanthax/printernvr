from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.printers import build_printer_cards

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    cameras = request.app.state.cameras
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cameras": [camera.model_dump() for camera in cameras],
        },
    )


@router.get("/cameras", response_class=HTMLResponse)
def camera_management_page(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "cameras.html",
        {
            "request": request,
        },
    )


@router.get("/clips", response_class=HTMLResponse)
def clips_page(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    cameras = request.app.state.cameras
    return templates.TemplateResponse(
        "clips.html",
        {
            "request": request,
            "cameras": [camera.model_dump() for camera in cameras],
            "initial_camera_id": request.query_params.get("camera_id", ""),
        },
    )


@router.get("/printers", response_class=HTMLResponse)
def printers_page(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    printer_cards = build_printer_cards(
        request.app.state.cameras,
        request.app.state.moonraker_service,
    )
    return templates.TemplateResponse(
        "printers.html",
        {
            "request": request,
            "printers": [card.model_dump(mode="json") for card in printer_cards],
        },
    )
