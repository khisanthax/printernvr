from __future__ import annotations

import logging
from datetime import timedelta
from urllib.parse import urlparse

import httpx

from app.models import PrinterStatusSnapshot

LOGGER = logging.getLogger(__name__)


class MoonrakerService:
    def __init__(self, timeout_seconds: float = 3.0) -> None:
        self._client = httpx.Client(timeout=timeout_seconds)

    def shutdown(self) -> None:
        self._client.close()

    def fetch_status(self, moonraker_url: str | None) -> PrinterStatusSnapshot:
        if not moonraker_url:
            return PrinterStatusSnapshot()

        try:
            request_url = _query_url(moonraker_url)
            response = self._client.get(request_url)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            request_url = moonraker_url
            LOGGER.warning("Moonraker status request failed for %s: %s", request_url, exc)
            return PrinterStatusSnapshot(
                connection_state="offline",
                printer_status_text="Offline",
                error_message=str(exc),
            )

        status_payload = payload.get("result", {}).get("status", {})
        if not isinstance(status_payload, dict):
            return PrinterStatusSnapshot(
                connection_state="online",
                printer_status_text="Status unavailable",
            )

        print_stats = _as_dict(status_payload.get("print_stats"))
        extruder = _as_dict(status_payload.get("extruder"))
        heater_bed = _as_dict(status_payload.get("heater_bed"))
        virtual_sdcard = _as_dict(status_payload.get("virtual_sdcard"))
        display_status = _as_dict(status_payload.get("display_status"))

        progress_ratio = _as_number(display_status.get("progress"))
        if progress_ratio is None:
            progress_ratio = _as_number(virtual_sdcard.get("progress"))
        progress_percent = round(progress_ratio * 100.0, 1) if progress_ratio is not None else None

        state = str(print_stats.get("state") or "").strip().lower()
        printer_status_text = _normalize_state_text(state)

        filename = str(print_stats.get("filename") or "").strip() or None
        if filename and "/" in filename:
            filename = filename.rsplit("/", 1)[-1]

        elapsed_seconds = _as_number(print_stats.get("print_duration"))
        if elapsed_seconds is None:
            elapsed_seconds = _as_number(print_stats.get("total_duration"))

        eta_text = None
        if state == "printing" and progress_ratio and progress_ratio > 0 and elapsed_seconds:
            remaining_seconds = max((elapsed_seconds / progress_ratio) - elapsed_seconds, 0.0)
            eta_text = _format_eta(remaining_seconds)

        return PrinterStatusSnapshot(
            connection_state="online",
            printer_status_text=printer_status_text,
            current_file_name=filename,
            progress_percent=progress_percent,
            extruder_current_temp=_as_number(extruder.get("temperature")),
            extruder_target_temp=_as_number(extruder.get("target")),
            bed_current_temp=_as_number(heater_bed.get("temperature")),
            bed_target_temp=_as_number(heater_bed.get("target")),
            eta_text=eta_text,
        )


def _query_url(base_url: str) -> str:
    raw_base = base_url.strip()
    if "://" not in raw_base:
        raw_base = f"http://{raw_base}"

    parsed = urlparse(raw_base)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid moonraker_url: {base_url}")

    prefix = f"{parsed.scheme}://{parsed.netloc}"
    base_path = parsed.path.rstrip("/")
    if base_path and base_path != "/":
        prefix = f"{prefix}{base_path}"
    return (
        f"{prefix}/printer/objects/query"
        "?print_stats&extruder&heater_bed&virtual_sdcard&display_status"
    )


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _as_number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_state_text(state: str) -> str:
    mapping = {
        "printing": "Printing",
        "paused": "Paused",
        "complete": "Complete",
        "standby": "Idle",
        "ready": "Idle",
        "cancelled": "Cancelled",
        "error": "Error",
    }
    return mapping.get(state, "Status unavailable")


def _format_eta(seconds: float) -> str:
    remaining = int(round(seconds))
    if remaining <= 0:
        return "0m"

    duration = timedelta(seconds=remaining)
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
