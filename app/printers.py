from __future__ import annotations

from collections import defaultdict

from app.models import PrinterCard, ResolvedCamera
from app.services.moonraker_service import MoonrakerService


def build_printer_cards(
    cameras: list[ResolvedCamera],
    moonraker_service: MoonrakerService,
) -> list[PrinterCard]:
    grouped: dict[str, list[ResolvedCamera]] = defaultdict(list)
    for camera in cameras:
        grouped[camera.printer_id].append(camera)

    cards: list[PrinterCard] = []
    for printer_id, grouped_cameras in grouped.items():
        primary = _select_primary_camera(grouped_cameras)
        preview_mode = _preview_mode(primary)
        preview_available = bool(primary.preview_url) if preview_mode != "none" else False

        status_camera = _select_status_camera(grouped_cameras)
        status = moonraker_service.fetch_status(status_camera.moonraker_url)

        cards.append(
            PrinterCard(
                printer_id=printer_id,
                printer_name=primary.printer_name,
                camera_id=primary.id,
                camera_name=primary.name,
                preview_url=primary.preview_url,
                preview_mode=preview_mode,
                preview_available=preview_available,
                connection_state=status.connection_state,
                printer_status_text=status.printer_status_text,
                current_file_name=status.current_file_name,
                progress_percent=status.progress_percent,
                extruder_current_temp=status.extruder_current_temp,
                extruder_target_temp=status.extruder_target_temp,
                bed_current_temp=status.bed_current_temp,
                bed_target_temp=status.bed_target_temp,
                eta_text=status.eta_text,
                available_camera_ids=[camera.id for camera in grouped_cameras],
                available_camera_count=len(grouped_cameras),
                moonraker_url=status_camera.moonraker_url,
                display_order=primary.display_order,
                error_message=status.error_message,
            )
        )

    cards.sort(key=_card_sort_key)
    return cards


def _select_primary_camera(cameras: list[ResolvedCamera]) -> ResolvedCamera:
    return sorted(cameras, key=_camera_sort_key)[0]


def _select_status_camera(cameras: list[ResolvedCamera]) -> ResolvedCamera:
    with_status = [camera for camera in cameras if camera.moonraker_url]
    if not with_status:
        return _select_primary_camera(cameras)
    return sorted(with_status, key=_camera_sort_key)[0]


def _camera_sort_key(camera: ResolvedCamera) -> tuple:
    return (
        0 if camera.enabled else 1,
        0 if camera.default_live_view else 1,
        0 if camera.preview_url else 1,
        camera.display_order if camera.display_order is not None else 9999,
        camera.name.lower(),
        camera.id.lower(),
    )


def _card_sort_key(card: PrinterCard) -> tuple:
    return (
        card.display_order if card.display_order is not None else 9999,
        card.printer_name.lower(),
        card.printer_id.lower(),
    )


def _preview_mode(camera: ResolvedCamera) -> str:
    if camera.mode == "gopro":
        if camera.preview_mode == "external_link" and camera.preview_url:
            return "external_link"
        return "none"
    if camera.preview_url:
        return "embedded"
    return "none"
