from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

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
