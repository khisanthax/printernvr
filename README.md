# Printer NVR

Printer NVR is a lightweight, Docker-first web app for monitoring and recording 3D printer cameras.

It is intentionally scoped to 3D printer workflows, not general CCTV management.

## Phase Coverage

This repository currently includes:
- Phase 0 foundation
- Phase 1 dashboard
- Phase 2 ffmpeg recording engine
- Phase 3 recording controls UI
- Phase 3A camera management UI
- Phase 4 clip browser
- Phase 4B clip preview and bulk direct download
- Phase 4A GoPro recorder support
- Phase 5 operational hardening improvements
- Phase 6 retention and storage protection

## Project Structure

```text
app/            FastAPI backend modules
config/         Camera config and app config JSON
recordings/     Output clips (bind mount)
logs/           Application logs (bind mount)
templates/      HTML templates
static/         CSS and JavaScript assets
docs/           Roadmap, architecture, and decisions
```

## Setup (Local Python)

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Optional: copy environment template:

```bash
cp .env.example .env
```

4. Ensure config files exist:

```bash
cp config/cameras.example.json config/cameras.json
cp config/app.example.json config/app.json
```

The example files are tracked in git. The live files `config/cameras.json` and `config/app.json` are intentionally untracked so local deployments can edit them without causing `git pull` conflicts.

5. Run the server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8787 --reload
```

Open `http://localhost:8787`.
Camera management is available at `http://localhost:8787/cameras`.
Clip browsing is available at `http://localhost:8787/clips`.

## Docker Run Instructions

1. Ensure `config/cameras.json` exists.
2. Ensure `config/app.json` exists.
3. Choose one option:

```bash
# Option A (recommended)
cp .env.example .env
```

```bash
# Option B
# Skip creating .env and use built-in defaults
```

4. Build and start:

```bash
docker compose up -d --build
```

The app is available at `http://localhost:8787` by default.
If `PORT` is set in `.env`, Docker Compose uses that host port.
Camera management is available at `/cameras`.
Clip browsing is available at `/clips`.

## Config Files and Git Pulls

Tracked config templates:
- `config/cameras.example.json`
- `config/app.example.json`

Local deployment config files:
- `config/cameras.json`
- `config/app.json`

The local deployment config files are not tracked by git. This avoids merge conflicts when a deployed host edits camera or app settings locally and later pulls repository updates.

One-time migration for older clones that still track these files:

```bash
git rm --cached config/cameras.json config/app.json
git commit -m "Stop tracking deployment-local config files"
```

After that, keep editing the local files normally.

## Environment Variables

From `.env` (optional):

- `PORT` default: `8787`
- `LOG_LEVEL` default: `info`
- `APP_CONFIG_PATH` default: `/app/config/cameras.json`
- `APP_APP_CONFIG_PATH` default: `/app/config/app.json`
- `APP_RECORDINGS_DIR` default: `/app/recordings`
- `APP_LOGS_DIR` default: `/app/logs`
- `APP_LOG_LEVEL` default: unset (falls back to `LOG_LEVEL`)

## Camera Configuration

Camera config is JSON at `config/cameras.json`.
The web UI can edit this file through `/cameras`, but the JSON file remains the source of truth.

Top-level format:

```json
{
  "cameras": []
}
```

### Mode 1: go2rtc Helper Mode

Provide:
- `go2rtc_base_url`
- optional `stream_name`

Example:

```json
{
  "id": "sv08_left",
  "name": "SV08 Left",
  "go2rtc_base_url": "http://printer.local:1984",
  "stream_name": "cam",
  "enabled": true,
  "output_subdir": "sv08_left"
}
```

Generated URLs:
- Preview: `http://printer.local:1984/stream.html?src=cam`
- Record: `rtsp://printer.local:8554/cam`

### Mode 2: Manual URL Mode

Provide explicit URLs:

```json
{
  "id": "sv08_right",
  "name": "SV08 Right",
  "preview_url": "http://printer-right.local:1984/stream.html?src=cam",
  "record_url": "rtsp://printer-right.local:8554/cam",
  "enabled": true,
  "output_subdir": "sv08_right"
}
```

### Resolution Rules

Preview resolution order:
1. Manual `preview_url`
2. go2rtc-generated preview URL
3. Dashboard shows `no preview configured`

Record resolution order:
1. Manual `record_url`
2. go2rtc-generated record URL

Manual URLs always override generated values.

### Mode 3: GoPro Mode

Provide GoPro-specific settings:

```json
{
  "id": "hero7_top",
  "name": "GoPro HERO7 Top",
  "mode": "gopro",
  "gopro_host": "10.5.5.9",
  "preview_mode": "external_link",
  "preview_url": "http://10.5.5.9:8080/live",
  "auto_download_after_stop": true,
  "download_timeout_seconds": 120,
  "file_stabilization_wait_seconds": 5,
  "enabled": true,
  "output_subdir": "hero7_top"
}
```

GoPro mode behavior:
- start and stop recording use the GoPro HTTP API
- clips are downloaded locally after stop
- downloaded clips land in the same `recordings/<camera_id>/` structure used by RTSP cameras
- preview is best-effort and currently supports `none` or `external_link`
- in-app stream proxy preview is not implemented in this version

## Camera Management UI

The `/cameras` page supports:
- listing current cameras
- adding new cameras
- editing existing cameras
- deleting cameras from config
- live preview while editing
- ffprobe-based stream testing

Behavior notes:
- camera ids auto-generate from the camera name when creating a new camera
- once the id field is edited manually, the UI stops auto-overwriting it
- deleting a camera removes it from config only
- actively recording cameras must be stopped before edit or delete
- the form warns if the recording URL looks like a browser preview stream, but does not block saving

### Preview URL vs Recording URL

Use `preview_url` for the browser-facing preview stream and `record_url` for the media stream consumed by `ffmpeg` and `ffprobe`.

Example preview URL:

```text
http://host:1984/stream.html?src=camera
```

Example recording URL:

```text
rtsp://host:8554/camera
```

In most go2rtc setups, the recording URL should be the RTSP stream or another ffmpeg-compatible media stream rather than the browser preview URL.

## App Configuration

App config is JSON at `config/app.json`.

Top-level example:

```json
{
  "retention": {
    "enabled": true,
    "cleanup_mode": "alert_only",
    "max_age_days": 30,
    "max_total_gb": 25,
    "minimum_free_gb": 5
  }
}
```

Retention settings:
- `enabled`
- `cleanup_mode`
- `max_age_days`
- `max_total_gb`
- `minimum_free_gb`

Cleanup modes:
- `disabled`: no warnings and no cleanup
- `alert_only`: compute warnings and cleanup candidates only
- `delete_oldest`: automatically delete oldest eligible files when thresholds are exceeded

Safety rules:
- Active recording outputs are never deleted
- Only completed local recordings under the recordings root are managed
- NAS or remote archival is not managed
- Cleanup actions are logged

## Recording Behavior

Recordings use the resolved `record_url` for the camera and are written locally beneath the configured recordings root in the camera `output_subdir`.
If `output_subdir` is not specified, it defaults to the camera id.

Recording compatibility defaults:
- RTSP inputs are opened with TCP transport by default
- MP4 clips record only the primary video stream
- audio and other side streams are not copied into printer clips by default

These defaults improve compatibility with go2rtc and camera streams that fail when ffmpeg tries to mux every stream into MP4.

GoPro recording behavior:
- GoPro does not record through ffmpeg
- the app sends GoPro shutter commands over HTTP
- timed GoPro recording uses an in-process worker thread
- after stop, the app waits briefly for file stabilization and downloads the resulting clip(s)

Filename format:

```text
<camera_id>_YYYYMMDD_HHMMSS.mp4
```

Example:

```text
sv08_left_20260307_154530.mp4
```

## Clip Browser

The `/clips` page scans the local recordings directory directly and shows:
- camera id
- filename
- relative path
- created timestamp
- file size
- active status

Behavior:
- newest clips are shown first
- clips can be filtered by camera
- clips can be previewed inline in the browser through a dedicated preview endpoint
- clips can be selected and bulk-downloaded as individual files from one user action
- downloads stream the file directly from disk
- delete removes only the selected local clip
- active recording files cannot be deleted

Bulk download notes:
- Printer NVR does not create ZIP archives for bulk clip download
- the browser triggers one direct download per selected file
- some browsers may ask permission before allowing multiple downloads

Clip APIs operate only within the configured local recordings root and reject invalid paths.

## API Endpoints

- `GET /health`
- `GET /api/cameras`
- `POST /api/cameras`
- `PUT /api/cameras/{camera_id}`
- `DELETE /api/cameras/{camera_id}`
- `POST /api/camera/probe`
- `POST /api/gopro/test`
- `GET /api/gopro/{camera_id}/status`
- `POST /api/gopro/{camera_id}/record_for`
- `POST /api/gopro/{camera_id}/download_latest`
- `GET /api/gopro/{camera_id}/preview`
- `GET /api/gopro/{camera_id}/media`
- `GET /api/status`
- `GET /api/record/status`
- `POST /api/record/start/{camera_id}`
- `POST /api/record/stop/{camera_id}`
- `GET /api/storage/status`
- `POST /api/storage/cleanup`
- `GET /api/clips`
- `GET /api/clips/preview/{camera_id}/{filename}`
- `GET /api/clips/download/{camera_id}/{filename}`
- `DELETE /api/clips/{camera_id}/{filename}`

`POST /api/record/start/{camera_id}` accepts an optional JSON body:

```json
{
  "duration": 60
}
```

`POST /api/storage/cleanup` performs manual cleanup only when retention is enabled and cleanup mode is not `disabled`.

The dashboard also shows storage usage, warning state, cleanup mode, and a manual cleanup button when retention cleanup is enabled.

## Notes

- ffmpeg is installed in the Docker image.
- The app starts even when zero cameras exist.
- Camera saves update the running app state without requiring a restart.
- Storage warnings are shown in the dashboard when retention thresholds are exceeded.
- Recording and probe failures now surface fuller ffmpeg and ffprobe diagnostics in the UI.
- No database, queue, NAS sync logic, or external scheduler is included.
