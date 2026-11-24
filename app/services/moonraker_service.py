from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from threading import Lock

import httpx

from app.models import PrinterStatusSnapshot
from app.media import redact_diagnostic

LOGGER = logging.getLogger(__name__)
LAST_READING_FIELDS = {
    "current_file_name", "progress_percent", "extruder_current_temp", "extruder_target_temp",
    "bed_current_temp", "bed_target_temp", "last_metadata_success_at",
}


class MoonrakerService:
    def __init__(self, timeout_seconds: float = 3.0) -> None:
        self._client = httpx.Client(timeout=timeout_seconds)
        self._status_lock = Lock()
        self._snapshots: dict[str, tuple[float, PrinterStatusSnapshot]] = {}

    def shutdown(self) -> None:
        self._client.close()

    def active_job_id(self, moonraker_url: str) -> str | None:
        try:
            endpoint = _query_url(moonraker_url).split("/printer/objects/query?", 1)[0]
            response = self._client.get(f"{endpoint}/server/history/list", params={"limit": 1, "order": "desc"})
            response.raise_for_status()
            job = response.json()["result"]["jobs"][0]
            if job.get("status") == "in_progress" and job.get("job_id") and job.get("start_time"):
                return f"{job['job_id']}:{job['start_time']}"
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            pass
        return None

    def fetch_status(self, moonraker_url: str | None) -> PrinterStatusSnapshot:
        if not moonraker_url:
            return PrinterStatusSnapshot()
        with self._status_lock:
            cached = self._snapshots.get(moonraker_url)
            if cached and time.monotonic() - cached[0] < 0.8:
                return cached[1].model_copy()
        status = self._read_status(moonraker_url)
        with self._status_lock:
            latest = self._snapshots.get(moonraker_url)
            if latest:
                previous = latest[1]
                if (previous.last_metadata_attempt_at and status.last_metadata_attempt_at
                        and previous.last_metadata_attempt_at > status.last_metadata_attempt_at):
                    return previous.model_copy()
                if not status.metadata_available:
                    status = status.model_copy(update=previous.model_dump(include=LAST_READING_FIELDS))
            self._snapshots[moonraker_url] = (time.monotonic(), status)
        return status.model_copy()

    def _read_status(self, moonraker_url: str) -> PrinterStatusSnapshot:

        attempted_at = datetime.now(timezone.utc)

        try:
            request_url = _query_url(moonraker_url)
            response = self._client.get(request_url)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            request_url = moonraker_url
            error = redact_diagnostic(str(exc), request_url)
            LOGGER.warning("Moonraker status request failed: %s", error)
            return PrinterStatusSnapshot(
                connection_state="offline",
                printer_status_text="Offline",
                monitor_state="offline",
                error_message=error,
                has_metadata_source=True,
                last_metadata_attempt_at=attempted_at,
            )

        result = _as_dict(_as_dict(payload).get("result"))
        status_payload = _as_dict(result.get("status"))
        eventtime = _as_number(result.get("eventtime"))
        print_stats = _as_dict(status_payload.get("print_stats"))
        state = str(print_stats.get("state") or "").strip().lower()
        if _monitor_state(state) == "unavailable":
            return PrinterStatusSnapshot(
                connection_state="online",
                printer_status_text="Status unavailable",
                monitor_state="unavailable",
                has_metadata_source=True,
                metadata_available=False,
                last_metadata_attempt_at=attempted_at,
            )

        layer = _as_dict(print_stats.get("info")).get("current_layer")
        extruder = _as_dict(status_payload.get("extruder"))
        heater_bed = _as_dict(status_payload.get("heater_bed"))
        virtual_sdcard = _as_dict(status_payload.get("virtual_sdcard"))
        display_status = _as_dict(status_payload.get("display_status"))

        progress_ratio = _as_number(display_status.get("progress"))
        if progress_ratio is None:
            progress_ratio = _as_number(virtual_sdcard.get("progress"))
        progress_percent = round(progress_ratio * 100.0, 1) if progress_ratio is not None else None

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
            klipper_eventtime=eventtime if eventtime is not None and eventtime >= 0 else None,
            current_layer=layer if type(layer) is int and layer > 0 else None,
            connection_state="online",
            printer_status_text=printer_status_text,
            monitor_state=_monitor_state(state),
            current_file_name=filename,
            progress_percent=progress_percent,
            extruder_current_temp=_as_number(extruder.get("temperature")),
            extruder_target_temp=_as_number(extruder.get("target")),
            bed_current_temp=_as_number(heater_bed.get("temperature")),
            bed_target_temp=_as_number(heater_bed.get("target")),
            eta_text=eta_text,
            has_metadata_source=True,
            metadata_available=True,
            last_metadata_attempt_at=attempted_at,
            last_metadata_success_at=attempted_at,
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
        number = float(value)
        return number if math.isfinite(number) else None
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


def _monitor_state(state: str) -> str:
    mapping = {
        "printing": "printing",
        "paused": "paused",
        "complete": "complete",
        "standby": "idle",
        "ready": "idle",
        "cancelled": "complete",
        "error": "error",
    }
    return mapping.get(state, "unavailable")


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
