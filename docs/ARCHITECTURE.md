# Printer NVR Architecture

## Scope

Printer NVR is a single-service, Docker-first application for 3D printer camera monitoring and recording.

Printers are stream providers only. Recording runs on the central Printer NVR host.

## Runtime Components

- FastAPI web server
- Jinja template rendering
- Static assets (plain CSS and minimal JavaScript)
- JSON configuration loader
- In-memory runtime camera state manager

## Current Module Layout

- `app/main.py`: app startup, settings, lifespan wiring, router registration
- `app/config.py`: config loading and camera URL resolution
- `app/models.py`: Pydantic models for config and runtime state
- `app/state.py`: runtime state manager for camera status
- `app/util.py`: logging and directory helpers
- `app/api/health.py`: health endpoint
- `app/api/dashboard.py`: dashboard page
- `app/api/cameras.py`: resolved camera list API
- `app/api/status.py`: runtime state API

## Data Flow

1. App starts and loads environment settings with defaults.
2. JSON camera config is read from `APP_CONFIG_PATH`.
3. Cameras are validated and resolved:
- manual URLs override generated URLs
- record URL must resolve
- preview URL can be missing
4. Runtime state is initialized (`idle` per camera).
5. Dashboard reads camera config server-side and polls `/api/status`.

## Camera URL Resolution

Supported camera input modes:
- go2rtc helper mode (`go2rtc_base_url`, optional `stream_name`)
- manual mode (`preview_url`, `record_url`)

Resolution rules:
- `record_url`: manual value, else generated go2rtc value (required)
- `preview_url`: manual value, else generated go2rtc preview, else unset
- If preview is unset, UI shows `no preview configured`

## Deployment Model

Docker Compose single container:
- image built from `Dockerfile`
- ffmpeg installed in container
- port mapping `${PORT:-8787}:8787`
- bind mounts:
- `./config -> /app/config`
- `./recordings -> /app/recordings`
- `./logs -> /app/logs`

Environment defaults allow startup without `.env`.

## Operational Notes

- App can start with zero cameras configured.
- Errors should be logged and reflected in runtime state.
- Phase 2 will add ffmpeg recording process lifecycle management.
