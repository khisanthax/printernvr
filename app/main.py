from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.cameras import router as cameras_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.record import router as record_router
from app.api.status import router as status_router
from app.api.storage import router as storage_router
from app.camera_store import CameraConfigStore
from app.config import load_app_config
from app.recorder import RecordingManager
from app.retention import RetentionManager
from app.state import RuntimeStateManager
from app.util import configure_logging, ensure_directories

LOGGER = logging.getLogger(__name__)


def _settings() -> dict[str, str]:
    log_level = os.getenv("APP_LOG_LEVEL") or os.getenv("LOG_LEVEL", "INFO")
    return {
        "camera_config_path": os.getenv("APP_CONFIG_PATH", "config/cameras.json"),
        "app_config_path": os.getenv("APP_APP_CONFIG_PATH", "config/app.json"),
        "recordings_dir": os.getenv("APP_RECORDINGS_DIR", "recordings"),
        "logs_dir": os.getenv("APP_LOGS_DIR", "logs"),
        "log_level": log_level,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = _settings()

    ensure_directories([settings["recordings_dir"], settings["logs_dir"]])
    configure_logging(settings["logs_dir"], settings["log_level"])

    loaded_config = load_app_config(
        settings["camera_config_path"],
        settings["app_config_path"],
    )
    runtime_state = RuntimeStateManager()
    runtime_state.initialize(loaded_config.cameras)

    camera_output_dirs = [
        os.path.join(settings["recordings_dir"], camera.output_subdir)
        for camera in loaded_config.cameras
        if camera.enabled
    ]
    ensure_directories(camera_output_dirs)

    retention_manager = RetentionManager(
        settings["recordings_dir"],
        loaded_config.retention,
    )

    def enforce_retention_after_recording() -> None:
        retention_manager.enforce_retention(
            runtime_state.active_output_paths(),
            triggered_by="recording_finished",
            manual=False,
        )

    recording_manager = RecordingManager(
        settings["recordings_dir"],
        runtime_state,
        on_recording_finished=enforce_retention_after_recording,
    )

    retention_manager.enforce_retention(
        runtime_state.active_output_paths(),
        triggered_by="startup",
        manual=False,
    )

    app.state.settings = settings
    app.state.cameras = loaded_config.cameras
    app.state.camera_index = {camera.id: camera for camera in loaded_config.cameras}
    app.state.runtime_state = runtime_state
    app.state.templates = Jinja2Templates(directory="templates")
    app.state.recording_manager = recording_manager
    app.state.retention_manager = retention_manager
    app.state.app_config = loaded_config
    app.state.camera_store = CameraConfigStore(settings["camera_config_path"])

    LOGGER.info("Printer NVR started with %d configured cameras", len(loaded_config.cameras))
    try:
        yield
    finally:
        recording_manager.shutdown()
        LOGGER.info("Printer NVR shutdown complete")


app = FastAPI(
    title="Printer NVR",
    description="Lightweight recording dashboard for 3D printer cameras",
    version="0.4.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(cameras_router)
app.include_router(status_router)
app.include_router(record_router)
app.include_router(storage_router)
