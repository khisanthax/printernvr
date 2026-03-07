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
from app.api.status import router as status_router
from app.config import load_app_config
from app.state import RuntimeStateManager
from app.util import configure_logging, ensure_directories

LOGGER = logging.getLogger(__name__)


def _settings() -> dict[str, str]:
    return {
        "config_path": os.getenv("APP_CONFIG_PATH", "config/cameras.json"),
        "recordings_dir": os.getenv("APP_RECORDINGS_DIR", "recordings"),
        "logs_dir": os.getenv("APP_LOGS_DIR", "logs"),
        "log_level": os.getenv("APP_LOG_LEVEL", "INFO"),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = _settings()

    ensure_directories([settings["recordings_dir"], settings["logs_dir"]])
    configure_logging(settings["logs_dir"], settings["log_level"])

    app_config = load_app_config(settings["config_path"])
    runtime_state = RuntimeStateManager()
    runtime_state.initialize(app_config.cameras)

    camera_output_dirs = [
        os.path.join(settings["recordings_dir"], camera.output_subdir)
        for camera in app_config.cameras
        if camera.enabled
    ]
    ensure_directories(camera_output_dirs)

    app.state.settings = settings
    app.state.cameras = app_config.cameras
    app.state.runtime_state = runtime_state
    app.state.templates = Jinja2Templates(directory="templates")

    LOGGER.info("Printer NVR started with %d configured cameras", len(app_config.cameras))
    yield
    LOGGER.info("Printer NVR shutdown complete")


app = FastAPI(
    title="Printer NVR",
    description="Lightweight recording dashboard for 3D printer cameras",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(cameras_router)
app.include_router(status_router)
