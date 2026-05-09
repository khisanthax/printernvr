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
- Phase 4C optional folder-targeted clip downloads
- Phase 8 live multi-printer dashboard
- Phase 8.1 per-printer camera view selector
- Phase 8.2 printer dashboard monitoring polish
- Phase 8.3 printer card recording controls
- Phase 8.4 printer card latest clip shortcuts
- Phase 8.5 custom printer card recording durations
- Phase 9 clip review and social export polish
- Phase 10 camera wall live view
- Phase 10.1 configurable camera wall grid density
- Phase 10.2 printer-first config and live wall refresh stability
- Phase 10.3 nested printers and cameras management UI
- Planned: Phase 10.4 optional secondary camera cards on `/live`
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
Compact camera wall viewing is available at `http://localhost:8787/live`.
Live printer monitoring is available at `http://localhost:8787/printers`.
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
Compact camera wall viewing is available at `/live`.
Live printer monitoring is available at `/printers`.
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

Preferred top-level format:

```json
{
  "printers": [
    {
      "id": "sv08",
      "name": "Sovol SV08",
      "enabled": true,
      "moonraker_url": "http://sv08.local",
      "display_order": 10,
      "default_camera_id": "sv08_front",
      "cameras": [
        {
          "id": "sv08_front",
          "name": "Front",
          "preview_url": "http://host:1984/stream.html?src=sv08_front",
          "record_url": "rtsp://host:8554/sv08_front",
          "display_order": 10,
          "enabled": true
        }
      ]
    }
  ]
}
```

Legacy top-level `cameras` configs still load for existing installs.
Printer NVR normalizes both config shapes internally, while recording routes and clips continue to use `camera_id`.
When saved through `/cameras`, config is written in the printer-first `printers` shape.

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

### Printer Grouping and Live Dashboard Fields

Printer-first config uses printer-level fields directly:
- `id`
- `name`
- `enabled`
- `moonraker_url`
- `display_order`
- `default_camera_id`
- nested `cameras`

Legacy camera-first config can still use optional grouping fields:

- `printer_id`
- `printer_name`
- `default_live_view`
- `moonraker_url`
- `display_order`

Behavior:
- cameras with the same `printer_id` are grouped into one printer card
- `default_live_view: true` marks the preferred live card camera for that printer
- if no camera is marked default, Printer NVR chooses the first enabled preview-capable camera
- if a printer has multiple configured cameras/views, `/printers` lets the browser choose between them while keeping the backend-computed default as the fallback
- `moonraker_url` is optional and, when set, is used to populate printer status, progress, temperatures, and ETA on the live printer page

### Legacy Compatibility: GoPro Mode

The codebase still contains legacy `mode: "gopro"` support for older configs, but it is deprecated and is not the recommended capture path for current deployments.

Current project direction is:
- go2rtc-assisted camera streams
- manual preview/record URL cameras
- live printer monitoring
- filesystem-based clip review and export workflow

## Camera Management UI

The `/cameras` page supports:
- listing printers with nested camera views
- adding, editing, and deleting printers
- adding, editing, and deleting cameras under a printer
- choosing the default camera per printer
- live preview while editing a camera
- ffprobe-based stream testing for camera recording URLs
- saving top-level `printers` config
- loading legacy top-level `cameras` config and migrating it to printer-first shape on save

Behavior notes:
- printer and camera ids auto-generate from names when creating new entries
- camera ids remain globally unique because recording and clips are camera-id based
- once the id field is edited manually, the UI stops auto-overwriting it
- deleting a printer or camera removes it from config only
- deleting config entries does not delete recordings or clips
- actively recording cameras must be stopped before config changes are saved
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
- favorite/rejected review state

Behavior:
- newest clips are shown first
- clips can be filtered by camera
- clips can be filtered by review state and searched by filename/camera/path
- clips can be marked as favorites/keepers
- clips can be marked as rejected without deleting them
- completed clips can be renamed safely inside their camera folder
- clips can be previewed inline in the browser through a dedicated preview endpoint
- clips can be selected and bulk-downloaded as individual files from one user action
- clips can optionally be saved into a user-selected folder when the browser supports the File System Access API
- downloads stream the file directly from disk
- delete removes only the selected local clip
- active recording files cannot be deleted

Bulk download notes:
- Printer NVR does not create ZIP archives for bulk clip download
- the browser triggers one direct download per selected file
- some browsers may ask permission before allowing multiple downloads

Optional chosen-folder download notes:
- this enhancement is client-side only and uses the browser File System Access API
- it works only in supporting Chromium-based browsers and only in secure contexts such as HTTPS or localhost
- when the browser allows it, the selected folder handle is restored from IndexedDB on later visits
- if support, permission, or direct-save fails, Printer NVR falls back to the normal browser download flow

Clip APIs operate only within the configured local recordings root and reject invalid paths.
Review metadata is stored as sidecar JSON under the recordings root. Printer NVR does not add a database, ZIP packaging, or export/copy helper for this workflow.

## Live Printer Dashboard

The `/printers` page shows one live card per printer.

Current behavior:
- one default camera/view per printer
- per-printer view selector when multiple camera previews exist
- large preview area
- enlarged modal preview for the currently selected view
- printer details shown below the preview
- top checkbox row for showing or hiding printer cards
- visibility persisted in browser `localStorage`
- selected view persisted per printer in browser `localStorage`
- optional Moonraker polling for printer status/details
- printer-state badges and per-card freshness text
- page-level and per-card status refresh buttons
- Start, Stop, quick timed recording buttons, and a custom duration field on each printer card
- latest clip shortcuts for the currently selected camera/view

View selection behavior:
- the backend still computes the default live camera using `default_live_view`, enabled state, preview availability, and `display_order`
- the browser may temporarily override that preview per printer card without changing config
- if the stored camera id is no longer valid, the card falls back to the backend default view
- recording controls always target the currently selected camera/view on that printer card

If `moonraker_url` is configured for a printer, the page attempts to show:
- printer status
- current file
- progress
- extruder temperature
- bed temperature
- ETA when it can be estimated

If Moonraker is not configured or unavailable:
- the card still renders
- preview still works when configured
- status fields fall back to placeholders
- freshness text falls back to `No metadata source` or `Waiting for successful refresh`

Monitoring polish notes:
- enlarged preview uses a lightweight modal overlay; it does not replace the card grid
- status badges are normalized to `Printing`, `Idle`, `Complete`, `Paused`, `Error`, `Offline`, or `Status unavailable`
- preview-unavailable and offline states are handled per card and do not affect other printers

Printer-card recording notes:
- `/printers` reuses the same `/api/record/start/{camera_id}`, `/api/record/stop/{camera_id}`, and `/api/record/status` endpoints used by the camera dashboard
- quick duration buttons support 10s, 15s, 20s, 30s, and 60s clips
- custom duration recording accepts 1-600 seconds from the card input
- all timed controls send the existing timed recording payload for the selected camera
- RTSP/go2rtc cameras still use the existing ffmpeg-based recording flow
- clips still appear in `/clips` through the existing filesystem-based storage model

Latest clip shortcut notes:
- each printer card shows the newest completed clip for the currently selected camera/view
- Preview Latest opens a lightweight video modal using the existing clip preview endpoint
- Download Latest uses the existing secure clip download endpoint
- View All Clips opens `/clips` filtered to the selected camera when possible
- latest clip data is filesystem-derived; no database or clip index is added

## Camera Wall

The `/live` page is a compact dark camera wall for watching all printers at once.

Current behavior:
- one compact card per printer
- live preview dominates each card
- status, progress, filename, temperatures, ETA, and freshness text stay below the video
- top visibility checkboxes show or hide printer cards
- visibility is persisted in browser `localStorage`
- cards per row can be set to Auto, 2, 3, or 4
- rows per screen can be set to Auto, 1, 2, or 3
- layout density is persisted in browser `localStorage`
- actively printing printers are sorted before non-printing printers
- per-printer view selector appears when multiple camera views exist
- selected view persistence is shared with `/printers`
- normal status polling updates text in place and does not reload camera iframes
- printing-priority sorting uses CSS ordering without moving mounted preview elements

By design, `/live` does not include recording controls, duration buttons, latest clip panels, or clip review actions. Those stay on `/printers` and `/clips`.

Planned follow-up:
- `/live` may optionally show a secondary camera view as a separate viewing-only card for printers with multiple cameras.
- This will not affect `/printers` selected-view persistence or recording target behavior.

## API Endpoints

- `GET /health`
- `GET /api/cameras`
- `GET /api/cameras/config`
- `PUT /api/cameras/config`
- `POST /api/cameras`
- `PUT /api/cameras/{camera_id}`
- `DELETE /api/cameras/{camera_id}`
- `POST /api/camera/probe`
- `GET /api/status`
- `GET /api/printers/cards`
- `GET /api/record/status`
- `POST /api/record/start/{camera_id}`
- `POST /api/record/stop/{camera_id}`
- `GET /api/storage/status`
- `POST /api/storage/cleanup`
- `GET /api/clips`
- `GET /api/clips/latest/{camera_id}`
- `PATCH /api/clips/{camera_id}/{filename}/metadata`
- `POST /api/clips/{camera_id}/{filename}/rename`
- `GET /api/clips/preview/{camera_id}/{filename}`
- `GET /api/clips/download/{camera_id}/{filename}`
- `DELETE /api/clips/{camera_id}/{filename}`
- `GET /live`

`POST /api/record/start/{camera_id}` accepts an optional JSON body:

```json
{
  "duration": 60
}
```

`POST /api/storage/cleanup` performs manual cleanup only when retention is enabled and cleanup mode is not `disabled`.

The dashboard also shows storage usage, warning state, cleanup mode, and a manual cleanup button when retention cleanup is enabled.

Deprecated compatibility note:
- Legacy GoPro endpoints still exist in the codebase for older configs, but they are not part of the active recommended workflow and are intentionally omitted from the main feature guidance above.

## Notes

- ffmpeg is installed in the Docker image.
- The app starts even when zero cameras exist.
- Camera saves update the running app state without requiring a restart.
- Storage warnings are shown in the dashboard when retention thresholds are exceeded.
- Recording and probe failures now surface fuller ffmpeg and ffprobe diagnostics in the UI.
- No database, queue, NAS sync logic, or external scheduler is included.
