# Printer NVR Architecture

## Scope

Printer NVR is a single-service, Docker-first application for 3D printer camera monitoring, recording, and local storage protection.

Printers are stream providers only. Recording and retention enforcement run on the central Printer NVR host.
GoPro devices are a separate recorder class controlled over their HTTP API, but still write clips back into the same local storage tree.

## Runtime Components

- FastAPI web server
- Jinja template rendering
- Static assets (plain CSS and minimal JavaScript)
- JSON configuration loader for camera config and app config
- In-memory runtime camera state manager
- ffmpeg subprocess recording manager
- GoPro HTTP service and in-process recording manager
- Local recordings retention manager
- Config-backed camera management UI
- Filesystem-based clip browser and preview/download/delete API

## Current Module Layout

- `app/main.py`: app startup, settings, lifespan wiring, router registration
- `app/config.py`: camera config loading, app config loading, URL resolution
- `app/camera_store.py`: safe camera config CRUD and config file writes
- `app/clips.py`: recordings filesystem scan, clip metadata, secure path resolution
- `app/models.py`: Pydantic models for config, runtime state, and storage status
- `app/state.py`: runtime state manager for camera recording state
- `app/recorder.py`: ffmpeg command building, process lifecycle, monitor threads
- `app/services/gopro_service.py`: HERO7 HTTP control, media listing, preview info, and clip download
- `app/services/gopro_recording_manager.py`: in-process GoPro job orchestration and auto-download
- `app/retention.py`: storage scanning, threshold evaluation, cleanup planning and deletion
- `app/probe.py`: ffprobe stream testing
- `app/util.py`: logging and directory helpers
- `app/api/health.py`: health endpoint
- `app/api/dashboard.py`: dashboard page
- `app/api/cameras.py`: camera CRUD and probe API
- `app/api/gopro.py`: GoPro test/status/media/preview/download endpoints
- `app/api/status.py`: legacy runtime status API
- `app/api/record.py`: recording start, stop, and status API
- `app/api/storage.py`: storage status and manual cleanup API
- `app/api/clips.py`: clip list, preview, download, and delete API

## Configuration Model

Two JSON files are used:

- `config/cameras.json`: camera definitions
- `config/app.json`: app-level settings such as retention
- `config/cameras.example.json` and `config/app.example.json`: tracked templates for new deployments

Camera definitions remain the source of truth even when edited through the web UI.
The `/cameras` page writes back to `config/cameras.json` rather than introducing a database.
The live `config/cameras.json` and `config/app.json` files are deployment-local and should remain untracked so host-specific edits do not block repository pulls.

Camera modes:
- `go2rtc_helper`
- `manual_urls`
- `gopro`

RTSP camera URL resolution:
- `record_url`: manual value, else generated go2rtc URL
- `preview_url`: manual value, else generated go2rtc preview URL, else unset

GoPro config behavior:
- `gopro_host` identifies the HERO7 on the local network
- `preview_mode` currently supports `none` and `external_link`
- `stream_proxy` is intentionally rejected until a clean in-app preview path exists
- GoPro clips are still written into `recordings/<output_subdir>/`

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
5. If the input is `rtsp://`, ffmpeg uses `-rtsp_transport tcp`.
6. Recording maps only the primary video stream into MP4:
- `-map 0:v:0`
- `-an`
- `-c:v copy`
7. Runtime state stores:
- `status`
- `recording`
- `started_at`
- `expected_end_at`
- `output_file`
- `output_path`
- `last_error`
- `last_error_details`
- `last_ffmpeg_command`
- `last_ffmpeg_exit_code`
- `last_completed_output`
8. A monitor thread captures full ffmpeg stderr and updates final state on exit.

This recording profile is intentionally conservative for printer cameras:
- RTSP over TCP improves compatibility with go2rtc and camera streams that are unreliable over default transport settings
- video-only MP4 output avoids mux failures caused by audio or non-video side streams

## GoPro Recording Flow

1. Client calls shared `POST /api/record/start/{camera_id}` or `POST /api/record/stop/{camera_id}` for a GoPro camera.
2. The record API dispatches by `camera.backend_type`.
3. `GoProRecordingManager` snapshots the pre-record media list, sends the HERO7 shutter command, and updates shared runtime state.
4. Timed GoPro recording uses an in-process background thread rather than ffmpeg `-t`.
5. Stop transitions through:
- stopping
- stabilization wait
- downloading
6. If `auto_download_after_stop` is enabled, media polling compares the new media list against the pre-record snapshot and downloads newly created video files into the normal recordings folder.
7. If snapshot comparison cannot identify a new file, the newest available video file is used as a fallback.

GoPro v1 preview behavior:
- no in-app stream proxy
- external preview links only when configured
- preview failures must not block record or download actions

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
5. RTSP stream probing uses `ffprobe` on the resolved `record_url` through `POST /api/camera/probe`.
6. If the probe input is `rtsp://`, ffprobe also uses TCP transport by default.
7. GoPro connectivity testing uses `POST /api/gopro/test`.
8. Probe results distinguish:
- input/open failure
- reachable stream with no video stream found
- reachable stream with a usable video stream

## Clip Browser Flow

1. `/clips` loads a lightweight template with an optional camera filter from the query string.
2. Browser-side JavaScript calls `GET /api/clips` and optionally filters by `camera_id`.
3. `ClipStore` scans the local recordings root directly from the filesystem.
4. Clip metadata includes:
- logical camera id
- filename
- relative path
- filesystem timestamp
- size
- active/in-use state
5. Inline preview uses `GET /api/clips/preview/{camera_id}/{filename}` with safe file resolution and browser-friendly media type handling.
6. Download uses `GET /api/clips/download/{camera_id}/{filename}` with `FileResponse`.
7. Manual delete uses `DELETE /api/clips/{camera_id}/{filename}` and is blocked for active recording outputs.
8. Bulk direct download is handled client-side in `/clips` by iterating selected clip download URLs from one user action; the backend still validates each file request individually.
9. Optional chosen-folder saves use the browser File System Access API entirely client-side:
- the browser prompts the user to choose a directory
- the frontend may persist the directory handle in IndexedDB when the browser allows it
- the backend never receives local filesystem path data
- if folder save is unavailable or fails, the UI falls back to the existing per-file browser download flow

Clip browser safety rules:
- only paths under the local recordings root are allowed
- camera id to storage directory resolution uses current camera config when available
- path traversal is rejected
- active files are never deleted
- missing files return a clean error instead of crashing the app
- clip preview uses a separate inline-serving endpoint instead of changing the attachment behavior of the download route
- bulk clip download does not generate ZIP archives or background jobs
- chosen-folder saves are a browser-only enhancement and require File System Access API support in a secure context

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
