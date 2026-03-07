# Printer NVR Architecture

## Scope

Printer NVR is a single-service, Docker-first application for 3D printer camera monitoring, recording, and local storage protection.

Printers are stream providers only. Recording and retention enforcement run on the central Printer NVR host.

## Runtime Components

- FastAPI web server
- Jinja template rendering
- Static assets (plain CSS and minimal JavaScript)
- JSON configuration loader for camera config and app config
- In-memory runtime camera state manager
- ffmpeg subprocess recording manager
- Local recordings retention manager

## Current Module Layout

- `app/main.py`: app startup, settings, lifespan wiring, router registration
- `app/config.py`: camera config loading, app config loading, URL resolution
- `app/models.py`: Pydantic models for config, runtime state, and storage status
- `app/state.py`: runtime state manager for camera recording state
- `app/recorder.py`: ffmpeg command building, process lifecycle, monitor threads
- `app/retention.py`: storage scanning, threshold evaluation, cleanup planning and deletion
- `app/util.py`: logging and directory helpers
- `app/api/health.py`: health endpoint
- `app/api/dashboard.py`: dashboard page
- `app/api/cameras.py`: resolved camera list API
- `app/api/status.py`: legacy runtime status API
- `app/api/record.py`: recording start, stop, and status API
- `app/api/storage.py`: storage status and manual cleanup API

## Configuration Model

Two JSON files are used:

- `config/cameras.json`: camera definitions
- `config/app.json`: app-level settings such as retention

Camera URL resolution:
- `record_url`: manual value, else generated go2rtc URL
- `preview_url`: manual value, else generated go2rtc preview URL, else unset

Retention config:
- `enabled`
- `cleanup_mode`
- `max_age_days`
- `max_total_gb`
- `minimum_free_gb`

## Recording Flow

1. Client calls `POST /api/record/start/{camera_id}`.
2. Backend validates camera existence, enabled state, and current recording state.
3. `RecordingManager` creates `/app/recordings/<output_subdir>/<camera_id>_YYYYMMDD_HHMMSS.mp4`, where `output_subdir` defaults to the camera id.
4. ffmpeg starts as a subprocess using the camera's resolved `record_url`.
5. Runtime state stores:
- `status`
- `recording`
- `started_at`
- `expected_end_at`
- `output_file`
- `output_path`
- `last_error`
- `last_completed_output`
6. A monitor thread captures ffmpeg stderr and updates final state on exit.

## Retention Flow

1. `RetentionManager` scans the local recordings directory only.
2. It computes:
- total recordings size
- free filesystem space
- eligible cleanup candidates
3. Active output paths from the runtime state are excluded from cleanup.
4. Warning thresholds are evaluated for:
- max file age
- total recordings size
- minimum free disk space
5. Automatic deletion occurs only when:
- retention is enabled
- cleanup mode is `delete_oldest`
6. Manual cleanup is exposed through `POST /api/storage/cleanup` when cleanup is enabled.

Cleanup behavior:
- delete oldest eligible files first
- delete only completed local recordings
- never delete currently active outputs
- log each deletion and any cleanup error

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
- Camera failures should set error state without crashing the app.
- Retention checks run on startup and after recording completion.
- No database, queue, scheduler, or NAS logic is included.
