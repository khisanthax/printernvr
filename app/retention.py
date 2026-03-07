from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

from app.models import CleanupSummary, RetentionConfig, StorageStatus

LOGGER = logging.getLogger(__name__)

BYTES_PER_GB = 1024 * 1024 * 1024


@dataclass
class RecordingFile:
    path: Path
    size_bytes: int
    modified_at: datetime


@dataclass
class PlannedDeletion:
    file: RecordingFile
    reason: str


class RetentionManager:
    def __init__(self, recordings_root: str, config: RetentionConfig) -> None:
        self._recordings_root = Path(recordings_root)
        self._config = config
        self._last_cleanup_summary: CleanupSummary | None = None
        self._lock = Lock()

    def get_storage_status(self, active_output_paths: set[str]) -> StorageStatus:
        files = self._scan_recording_files()
        total_bytes = sum(item.size_bytes for item in files)
        disk_usage = shutil.disk_usage(self._recordings_root)
        warnings = self._build_warnings(total_bytes, disk_usage.free)
        plan = self._build_cleanup_plan(files, total_bytes, disk_usage.free, active_output_paths)

        return StorageStatus(
            recordings_root=str(self._recordings_root),
            total_recordings_bytes=total_bytes,
            total_recordings_gb=self._to_gb(total_bytes),
            free_disk_bytes=disk_usage.free,
            free_disk_gb=self._to_gb(disk_usage.free),
            retention_enabled=self._config.enabled,
            cleanup_mode=self._config.cleanup_mode,
            warning_state=bool(warnings),
            warnings=warnings,
            candidate_cleanup_file_count=len(plan),
            last_cleanup_summary=self._last_cleanup_summary,
        )

    def enforce_retention(
        self,
        active_output_paths: set[str],
        triggered_by: str,
        manual: bool = False,
    ) -> CleanupSummary | None:
        if not self._config.enabled:
            if manual:
                raise ValueError("Manual cleanup is disabled")
            return None
        if not manual and self._config.cleanup_mode != "delete_oldest":
            status = self.get_storage_status(active_output_paths)
            for warning in status.warnings:
                LOGGER.warning("Retention warning: %s", warning)
            return None
        if manual and self._config.cleanup_mode == "disabled":
            raise ValueError("Manual cleanup is disabled")

        files = self._scan_recording_files()
        total_bytes = sum(item.size_bytes for item in files)
        disk_usage = shutil.disk_usage(self._recordings_root)
        plan = self._build_cleanup_plan(files, total_bytes, disk_usage.free, active_output_paths)

        summary = CleanupSummary(
            timestamp=datetime.utcnow(),
            triggered_by=triggered_by,
            cleanup_mode=self._config.cleanup_mode,
        )

        if not plan:
            with self._lock:
                self._last_cleanup_summary = summary
            return summary

        for warning in self._build_warnings(total_bytes, disk_usage.free):
            LOGGER.warning("Retention warning: %s", warning)

        for planned in plan:
            file_path = planned.file.path
            try:
                file_path.unlink(missing_ok=True)
                if not file_path.exists():
                    summary.deleted_files += 1
                    summary.deleted_bytes += planned.file.size_bytes
                    summary.deleted_paths.append(str(file_path))
                    if planned.reason not in summary.reasons:
                        summary.reasons.append(planned.reason)
                    LOGGER.info(
                        "Deleted recording %s (%s)",
                        file_path,
                        planned.reason,
                    )
            except OSError as exc:
                error = f"{file_path}: {exc}"
                summary.errors.append(error)
                LOGGER.warning("Retention delete failed: %s", error)

        summary.deleted_gb = self._to_gb(summary.deleted_bytes)
        with self._lock:
            self._last_cleanup_summary = summary
        return summary

    def _build_warnings(self, total_bytes: int, free_bytes: int) -> list[str]:
        if not self._config.enabled or self._config.cleanup_mode == "disabled":
            return []

        warnings: list[str] = []
        if self._config.max_total_gb is not None:
            max_total_bytes = int(self._config.max_total_gb * BYTES_PER_GB)
            if total_bytes > max_total_bytes:
                warnings.append(
                    "Recordings storage exceeds configured max_total_gb threshold."
                )
        if self._config.minimum_free_gb is not None:
            minimum_free_bytes = int(self._config.minimum_free_gb * BYTES_PER_GB)
            if free_bytes < minimum_free_bytes:
                warnings.append(
                    "Filesystem free space is below configured minimum_free_gb threshold."
                )
        if self._config.max_age_days is not None:
            cutoff = datetime.utcnow() - timedelta(days=self._config.max_age_days)
            for item in self._scan_recording_files():
                if item.modified_at < cutoff:
                    warnings.append(
                        "Some recordings exceed the configured max_age_days threshold."
                    )
                    break
        return warnings

    def _build_cleanup_plan(
        self,
        files: list[RecordingFile],
        total_bytes: int,
        free_bytes: int,
        active_output_paths: set[str],
    ) -> list[PlannedDeletion]:
        if not self._config.enabled or self._config.cleanup_mode == "disabled":
            return []

        normalized_active = {str(Path(path).resolve()) for path in active_output_paths}
        eligible = [
            item
            for item in sorted(files, key=lambda entry: entry.modified_at)
            if str(item.path.resolve()) not in normalized_active
        ]

        if not eligible:
            return []

        planned: list[PlannedDeletion] = []
        planned_paths: set[Path] = set()
        projected_total = total_bytes
        projected_free = free_bytes

        if self._config.max_age_days is not None:
            cutoff = datetime.utcnow() - timedelta(days=self._config.max_age_days)
            for item in eligible:
                if item.modified_at < cutoff:
                    planned.append(PlannedDeletion(file=item, reason="max_age_days"))
                    planned_paths.add(item.path)
                    projected_total -= item.size_bytes
                    projected_free += item.size_bytes

        for item in eligible:
            if item.path in planned_paths:
                continue

            reasons: list[str] = []
            if self._config.max_total_gb is not None:
                max_total_bytes = int(self._config.max_total_gb * BYTES_PER_GB)
                if projected_total > max_total_bytes:
                    reasons.append("max_total_gb")
            if self._config.minimum_free_gb is not None:
                minimum_free_bytes = int(self._config.minimum_free_gb * BYTES_PER_GB)
                if projected_free < minimum_free_bytes:
                    reasons.append("minimum_free_gb")

            if not reasons:
                continue

            planned.append(PlannedDeletion(file=item, reason="+".join(reasons)))
            planned_paths.add(item.path)
            projected_total -= item.size_bytes
            projected_free += item.size_bytes

        return planned

    def _scan_recording_files(self) -> list[RecordingFile]:
        if not self._recordings_root.exists():
            return []

        files: list[RecordingFile] = []
        for path in self._recordings_root.rglob("*"):
            if not path.is_file():
                continue
            try:
                stat_result = path.stat()
            except OSError as exc:
                LOGGER.warning("Unable to stat recording file %s: %s", path, exc)
                continue
            files.append(
                RecordingFile(
                    path=path,
                    size_bytes=stat_result.st_size,
                    modified_at=datetime.utcfromtimestamp(stat_result.st_mtime),
                )
            )
        return files

    def _to_gb(self, size_bytes: int) -> float:
        return round(size_bytes / BYTES_PER_GB, 3)
