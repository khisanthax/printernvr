from __future__ import annotations

from fastapi import APIRouter, Request

from app.printers import build_printer_cards

router = APIRouter(prefix="/api/printers", tags=["printers"])


@router.get("/cards")
def get_printer_cards(request: Request) -> dict:
    cards = build_printer_cards(
        request.app.state.cameras,
        request.app.state.moonraker_service,
    )
    return {"printers": [card.model_dump(mode="json") for card in cards]}
