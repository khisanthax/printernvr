from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
from typing import Callable

from app.models import GoProDownloadResult, GoProMediaItem, GoProPreviewResult, GoProStatusResult, ResolvedCamera
from app.services.gopro_service import GoProService, GoProServiceError
from app.state import RuntimeStateManager

LOGGER = logging.getLogger(__name__)


@dataclass
class GoProSession:
    camera: ResolvedCamera
    media_snapshot: set[str]
    started_at: datetime
    requested_duration_seconds: int | None = None
    phase: str = "recording"
    stop_requested: bool = False
    timer_thread: Thread | None = None
    worker_thread: Thread | None = None


class GoProRecordingManager:
    def __init__(
        self,
        recordings_root: str,
        runtime_state: RuntimeStateManager,
        service: GoProService,
        on_recording_finished: Callable[[], None] | None = None,
    ) -> None:
        self._recordings_root = Path(recordings_root)
        self._runtime_state = runtime_state
        self._service = service
        self._on_recording_finished = on_recording_finished
        self._lock = Lock()
        self._sessions: dict[str, GoProSession] = {}

    def is_busy(self, camera_id: str) -> bool:
        with self._lock:
            return camera_id in self._sessions

    def start_recording(self, camera: ResolvedCamera, duration: int | None = None):
        self._validate_camera(camera)
        with self._lock:
            if camera.id in self._sessions:
                raise ValueError(f"Camera '{camera.id}' already has a GoPro job in progress")

        media_snapshot = self._capture_snapshot(camera)
        started_at = datetime.utcnow()
        expected_end_at = (
            started_at + timedelta(seconds=duration) if duration is not None else None
        )
        self._runtime_state.mark_starting(
            camera.id,
            requested_duration_seconds=duration,
            message="Starting GoPro recording",
        )

        try:
            self._service.start_recording(camera)
        except GoProServiceError as exc:
            self._runtime_state.mark_error(
                camera.id,
                f"Failed to start GoPro recording: {exc.message}",
                details=exc.details or exc.command,
            )
            raise ValueError(f"Failed to start GoPro recording: {exc.message}") from exc

        session = GoProSession(
            camera=camera,
            media_snapshot=media_snapshot,
            started_at=started_at,
            requested_duration_seconds=duration,
        )
        with self._lock:
            self._sessions[camera.id] = session

        state = self._runtime_state.mark_recording_started(
            camera.id,
            started_at=started_at,
            expected_end_at=expected_end_at,
            requested_duration_seconds=duration,
            message="GoPro recording active",
        )

        if duration is not None:
            timer_thread = Thread(
                target=self._run_timed_recording,
                args=(camera.id, duration),
                daemon=True,
                name=f"gopro-record-for-{camera.id}",
            )
            session.timer_thread = timer_thread
            timer_thread.start()

        return state

    def stop_recording(self, camera_id: str):
        session = self._claim_stop(camera_id)
        if not session:
            raise ValueError(f"Camera '{camera_id}' is not currently recording")

        self._runtime_state.mark_stopping(camera_id, message="Stopping GoPro recording")
        worker = Thread(
            target=self._stop_and_download,
            args=(session,),
            daemon=True,
            name=f"gopro-stop-{camera_id}",
        )
        session.worker_thread = worker
        worker.start()
        return self._runtime_state.get_state(camera_id)

    def record_for(self, camera: ResolvedCamera, seconds: int):
        return self.start_recording(camera, duration=seconds)

    def download_latest(self, camera: ResolvedCamera) -> GoProDownloadResult:
        self._validate_camera(camera)
        if self.is_busy(camera.id):
            raise ValueError(f"Camera '{camera.id}' already has a GoPro job in progress")

        self._runtime_state.mark_downloading(camera.id, message="Downloading latest GoPro media")
        try:
            media_items = self._service.list_media(camera)
            candidates = self._service.find_latest_video(camera, media_items, None)
            if not candidates:
                raise ValueError("No GoPro video files were found to download")
            saved_paths = self._download_media_items(camera, candidates[:1])
        except (GoProServiceError, ValueError) as exc:
            details = exc.details if isinstance(exc, GoProServiceError) else str(exc)
            self._runtime_state.mark_error(
                camera.id,
                f"Failed to download latest GoPro clip: {exc}",
                details=details,
                last_download_status="Download failed",
            )
            raise ValueError(f"Failed to download latest GoPro clip: {exc}") from exc

        newest = saved_paths[-1].name if saved_paths else None
        self._runtime_state.mark_recording_stopped(
            camera.id,
            last_completed_output=newest,
            last_downloaded_filename=newest,
            last_download_status=f"Downloaded {len(saved_paths)} file(s)",
            message="Latest GoPro clip downloaded",
        )
        self._notify_finished()
        return GoProDownloadResult(
            success=True,
            camera_id=camera.id,
            downloaded_files=[path.name for path in saved_paths],
            message="Latest GoPro clip downloaded",
        )

    def get_status(self, camera: ResolvedCamera) -> GoProStatusResult:
        self._validate_camera(camera)
        return self._service.get_status(camera)

    def list_media(self, camera: ResolvedCamera) -> list[GoProMediaItem]:
        self._validate_camera(camera)
        return self._service.list_media(camera)

    def get_preview_info(self, camera: ResolvedCamera) -> GoProPreviewResult:
        self._validate_camera(camera)
        return self._service.get_preview_info(camera)

    def shutdown(self) -> None:
        LOGGER.info("GoPro recording manager shutdown")

    def _run_timed_recording(self, camera_id: str, seconds: int) -> None:
        remaining = seconds
        while remaining > 0:
            time.sleep(1)
            remaining -= 1
            with self._lock:
                session = self._sessions.get(camera_id)
                if not session or session.stop_requested or session.phase != "recording":
                    return

        session = self._claim_stop(camera_id)
        if not session:
            return

        self._runtime_state.mark_stopping(
            camera_id,
            message=f"Timed GoPro recording finished after {seconds}s",
        )
        self._stop_and_download(session)

    def _claim_stop(self, camera_id: str) -> GoProSession | None:
        with self._lock:
            session = self._sessions.get(camera_id)
            if not session or session.phase != "recording":
                return None
            session.phase = "stopping"
            session.stop_requested = True
            return session

    def _capture_snapshot(self, camera: ResolvedCamera) -> set[str]:
        try:
            items = self._service.list_media(camera)
            return {item.relative_key for item in items}
        except GoProServiceError as exc:
            LOGGER.warning(
                "GoPro media snapshot failed before start: camera=%s host=%s error=%s",
                camera.id,
                camera.gopro_host,
                exc,
            )
            return set()

    def _stop_and_download(self, session: GoProSession) -> None:
        camera = session.camera
        try:
            self._service.stop_recording(camera)
            self._service.sleep_for_stabilization(camera)
            if camera.auto_download_after_stop:
                self._runtime_state.mark_downloading(
                    camera.id,
                    message="Downloading GoPro clip",
                )
                media_items = self._poll_for_media(camera, session.media_snapshot)
                saved_paths = self._download_media_items(camera, media_items)
                newest = saved_paths[-1].name if saved_paths else None
                message = f"Downloaded {len(saved_paths)} GoPro file(s)"
                self._runtime_state.mark_recording_stopped(
                    camera.id,
                    last_completed_output=newest,
                    last_downloaded_filename=newest,
                    last_download_status=message,
                    message=message,
                )
            else:
                self._runtime_state.mark_recording_stopped(
                    camera.id,
                    last_download_status="Auto-download disabled",
                    message="GoPro recording stopped",
                )
        except GoProServiceError as exc:
            self._runtime_state.mark_error(
                camera.id,
                f"GoPro action failed: {exc.message}",
                details=exc.details or exc.command,
                last_download_status="Download failed"
                if session.camera.auto_download_after_stop
                else None,
            )
        except ValueError as exc:
            self._runtime_state.mark_error(
                camera.id,
                f"GoPro action failed: {exc}",
                details=str(exc),
                last_download_status="Download failed"
                if session.camera.auto_download_after_stop
                else None,
            )
        finally:
            with self._lock:
                current = self._sessions.get(camera.id)
                if current is session:
                    self._sessions.pop(camera.id, None)
            self._notify_finished()

    def _poll_for_media(
        self,
        camera: ResolvedCamera,
        previous_snapshot: set[str],
    ) -> list[GoProMediaItem]:
        deadline = time.time() + camera.download_timeout_seconds
        fallback_items: list[GoProMediaItem] = []
        while time.time() < deadline:
            media_items = self._service.list_media(camera)
            candidates = self._service.find_latest_video(camera, media_items, previous_snapshot)
            if candidates:
                if previous_snapshot:
                    new_candidates = [
                        item
                        for item in candidates
                        if item.relative_key not in previous_snapshot and item.is_video
                    ]
                    if new_candidates:
                        return new_candidates
                fallback_items = candidates
            time.sleep(2)

        if fallback_items:
            return fallback_items
        raise ValueError("No new GoPro media file appeared before download timeout")

    def _download_media_items(
        self,
        camera: ResolvedCamera,
        media_items: list[GoProMediaItem],
    ) -> list[Path]:
        destination_dir = self._recordings_root / camera.output_subdir
        saved_paths: list[Path] = []
        for item in media_items:
            if not item.is_video:
                continue
            saved_paths.append(self._service.download_media(camera, item, destination_dir))
        if not saved_paths:
            raise ValueError("No GoPro video file was available to download")
        saved_paths.sort(key=lambda path: path.name)
        return saved_paths

    def _notify_finished(self) -> None:
        if self._on_recording_finished:
            try:
                self._on_recording_finished()
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("GoPro post-recording callback failed: %s", exc)

    def _validate_camera(self, camera: ResolvedCamera) -> None:
        if camera.mode != "gopro" or camera.backend_type != "gopro":
            raise ValueError(f"Camera '{camera.id}' is not a GoPro camera")
        if not camera.enabled:
            raise ValueError(f"Camera '{camera.id}' is disabled")
