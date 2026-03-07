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
- Config-backed camera management UI

## Current Module Layout

- `app/main.py`: app startup, settings, lifespan wiring, router registration
- `app/config.py`: camera config loading, app config loading, URL resolution
- `app/camera_store.py`: safe camera config CRUD and config file writes
- `app/models.py`: Pydantic models for config, runtime state, and storage status
- `app/state.py`: runtime state manager for camera recording state
- `app/recorder.py`: ffmpeg command building, process lifecycle, monitor threads
- `app/retention.py`: storage scanning, threshold evaluation, cleanup planning and deletion
- `app/probe.py`: ffprobe stream testing
- `app/util.py`: logging and directory helpers
- `app/api/health.py`: health endpoint
- `app/api/dashboard.py`: dashboard page
- `app/api/cameras.py`: camera CRUD and probe API
- `app/api/status.py`: legacy runtime status API
- `app/api/record.py`: recording start, stop, and status API
- `app/api/storage.py`: storage status and manual cleanup API

## Configuration Model

Two JSON files are used:

- `config/cameras.json`: camera definitions
- `config/app.json`: app-level settings such as retention

Camera definitions remain the source of truth even when edited through the web UI.
The `/cameras` page writes back to `config/cameras.json` rather than introducing a database.

Camera URL resolution:
- `record_url`: manual value, else generated go2rtc URL
- `preview_url`: manual value, else generated go2rtc preview URL, else unset

Preview and recording URLs are intentionally different concerns:
- `preview_url` should be browser-compatible and is used only for UI preview rendering
- `record_url` should be ffmpeg/ffprobe-compatible and is used for recording and probing
- the camera management UI warns when a `record_url` looks like a preview-style URL, but this is heuristic guidance only and does not block saving

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

## Camera Management Flow

1. `/cameras` loads the current camera list from `GET /api/cameras`.
2. Browser-side form logic handles:
- id auto-generation from name
- mode-specific fields
- preview URL derivation for live preview
- heuristic warning when the effective recording URL looks like a browser preview stream
3. Save and delete requests update `config/cameras.json` through `CameraConfigStore`.
4. After each successful write, the running app refreshes:
- `app.state.cameras`
- `app.state.camera_index`
- runtime camera state entries
5. Stream probing uses `ffprobe` on the resolved `record_url` through `POST /api/camera/probe`.

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
