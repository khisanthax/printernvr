# Printer NVR Roadmap

This document tracks the implementation roadmap for **Printer NVR** and serves as the working reference for phased development.

## Project Overview

Printer NVR is a lightweight web-based recording system for multiple 3D printer cameras.

Each printer exposes its camera stream through go2rtc. Printer NVR provides a web UI where users can view printer cameras and manually record short clips.

Users should be able to:
- View multiple printer camera streams
- Start recording manually
- Stop recording manually
- Record for a fixed duration that stops automatically

Printer NVR is not intended to be a general CCTV platform. It is designed specifically for 3D printer workflows.

## Key Architecture Rules

- Printers only provide camera streams.
- Recording happens on a central recorder host.
- ffmpeg runs on the recorder host.
- Recordings are stored locally on the recorder host.
- NAS syncing is not part of application logic.
- Docker-first deployment.
- GitHub-ready repository from day one.

## Camera Input Model (Updated)

Printer NVR supports three camera configuration modes.

### Mode 1: go2rtc-assisted setup

User provides:
- `go2rtc_base_url`
- optional `stream_name`

Example:

```json
{
  "id": "sv08_left",
  "name": "SV08 Left",
  "go2rtc_base_url": "http://sv08-left.local:1984",
  "stream_name": "cam",
  "enabled": true,
  "output_subdir": "sv08_left"
}
```

Application derives likely URLs:
- Preview example: `http://sv08-left.local:1984/stream.html?src=cam`
- Record example: `rtsp://sv08-left.local:8554/cam`

This is a convenience helper, not a requirement.

### Mode 2: manual stream configuration

User provides explicit URLs.

```json
{
  "id": "sv08_left",
  "name": "SV08 Left",
  "preview_url": "http://sv08-left.local:1984/stream.html?src=cam",
  "record_url": "rtsp://sv08-left.local:8554/cam",
  "enabled": true,
  "output_subdir": "sv08_left"
}
```

Manual values override auto-generated ones.

### Mode 3: GoPro API-controlled recording

User provides explicit GoPro device settings.

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

GoPro cameras:
- do not record through ffmpeg
- are controlled through the GoPro HTTP API
- download clips back into the normal local recordings directory after stop
- may use an external preview link when in-app live preview is not practical

### Configuration Priority

Order of precedence:
1. Manual URLs
2. Generated go2rtc URLs
3. Preview may be unset and shown as `no preview configured` in the dashboard

### Camera Configuration Fields

Supported fields:
- `id`
- `name`
- `enabled`
- `description`
- `printer_id`
- `printer_name`
- `default_live_view`
- `moonraker_url`
- `display_order`
- `mode`
- `go2rtc_base_url`
- `stream_name`
- `preview_url`
- `record_url`
- `gopro_host`
- `preview_mode`
- `auto_download_after_stop`
- `download_timeout_seconds`
- `file_stabilization_wait_seconds`
- `output_subdir`

## Updated Phased Roadmap

Status key:
- `[ ]` Not started
- `[-]` In progress
- `[x]` Complete

### Phase 0 - Project Foundation [x]

Goals:
- GitHub-ready repository
- Docker-first deployment
- Config loading
- Camera model
- go2rtc helper logic
- Minimal dashboard
- Health endpoint

Tasks:
- Create repo structure
- Dockerfile
- docker-compose
- README
- LICENSE
- Config schema
- Camera config parser
- go2rtc URL generator
- Dashboard skeleton
- Preview cards
- Logging
- Startup validation

Deliverables:
- Working Docker deployment
- Health endpoint
- Config loader
- Camera parsing
- Dashboard showing cameras

### Phase 1 - Camera Dashboard [x]

Goals:
- Display configured cameras
- Preview streams
- Show runtime status
- Prepare UI for recording controls

Tasks:
- Camera cards
- Preview embed
- Runtime state manager
- API endpoints
- Polling for state
- Responsive layout

Deliverables:
- Working dashboard
- Config-driven cameras
- API endpoints
- Preview display
- Placeholder controls

### Phase 2 - Recording Engine [x]

Goals:
- Implement ffmpeg recording
- Manual start/stop
- Timed recording

Tasks:
- Recording manager
- ffmpeg subprocess control
- Process tracking
- Recording state management

Deliverables:
- Recording API
- Start/stop recording
- Timed recording
- Local file storage

### Phase 3 - UI Controls [x]

Goals:
- Connect UI buttons to recording engine

Controls:
- Start
- Stop
- 30s
- 60s
- 120s
- Custom duration

Deliverables:
- Live recording control
- UI state updates

### Phase 3A - Camera Management [x]

Goals:
- Add a camera management page in the web UI
- Allow add, edit, delete, preview, and probe without manual file editing
- Keep camera config file based and lightweight

Tasks:
- Camera management page
- Config-backed CRUD endpoints
- Safe writes to `config/cameras.json`
- Live preview panel while editing
- ffprobe-based stream testing
- In-memory camera reload after save/delete

Deliverables:
- `/cameras` management page
- Camera create/update/delete from browser
- Live preview while editing
- ffprobe stream test endpoint
- Dashboard reflects camera config changes without restart

### Phase 4 - Clip Management [x]

Goals:
- View recorded clips
- Download clips

Tasks:
- File listing
- Metadata display
- Download links
- Optional delete

Deliverables:
- `/clips` page
- Filesystem-based clip browser
- Download endpoint
- Manual clip deletion with active-file protection

### Phase 4B - Clip Preview and Bulk Direct Download [x]

Goals:
- Preview clips inline in the browser before downloading
- Support selecting multiple clips from the current clip list
- Trigger one-click bulk direct download of selected clips as individual files

Tasks:
- Add clip preview endpoint for inline playback
- Add per-clip preview toggle in `/clips`
- Add checkbox selection UI with select-all and clear actions
- Add client-side bulk direct download behavior without ZIP packaging

Deliverables:
- Inline clip preview on `/clips`
- Multi-select clip actions
- One-click bulk direct download as separate files
- Existing single download and delete actions preserved

### Phase 4C - Optional Folder-Targeted Clip Downloads [x]

Goals:
- Allow users on supported browsers to choose a download folder for clips
- Keep all folder selection client-side with no backend path tracking
- Fall back cleanly to normal browser downloads when unsupported or denied

Tasks:
- Add folder selection controls on `/clips`
- Use the browser File System Access API when available
- Persist the folder handle in browser storage when the browser allows it
- Keep per-file and bulk download fallback behavior unchanged

Deliverables:
- Optional chosen-folder clip downloads on `/clips`
- Session or IndexedDB-backed folder-handle reuse depending on browser support
- Graceful fallback to standard browser downloads

### Phase 4A - GoPro Recorder Support [x]

Goals:
- Support GoPro as a separate recording backend
- Start and stop GoPro recording from the dashboard
- Automatically download completed GoPro clips into local storage
- Keep clip browsing and storage model unchanged

Tasks:
- Extend camera config for `mode=gopro`
- Add GoPro connectivity testing
- Add GoPro start/stop/record-for/download API
- Add in-process GoPro recording manager
- Add GoPro dashboard controls
- Add external preview fallback

Deliverables:
- GoPro camera management support
- Shared `/api/record` dispatch for RTSP and GoPro cameras
- Automatic clip download after GoPro stop
- One-click 30-second GoPro recording
- Existing clip browser listing downloaded GoPro clips

### Phase 8 - Live Multi-Printer Dashboard [x]

Goals:
- Add a live printer overview page with one card per printer
- Show printer details below each live preview instead of overlaying them on video
- Allow users to toggle visible printer cards from a top control area
- Support one default live camera per printer in this phase

Tasks:
- Add `/printers` page and printer-card grid
- Group cameras into printers using lightweight config fields
- Choose one default live camera per printer
- Add printer visibility toggles with browser persistence
- Add optional Moonraker-backed status polling for card details

Deliverables:
- Live printer dashboard page
- Klipper-style printer cards with details beneath preview
- Printer visibility checkboxes with client-side persistence
- Optional printer status/progress/temperature details when Moonraker is configured

### Phase 8A - Multi-View Per Printer [x]

Goals:
- Add a per-printer camera/view selector
- Support alternate live angles for the same printer without leaving the live page

Tasks:
- Add per-printer camera selector UI
- Switch live preview within the printer card
- Preserve a default view while allowing temporary alternate selection

Deliverables:
- Compact per-printer view selector on `/printers` when multiple views exist
- Browser-side view persistence per printer in `localStorage`
- Default live view remains the backend fallback when no stored selection is valid

### Phase 5 - Operational Hardening [-]

Goals:
- Reliability
- Logging
- Startup checks
- Camera failure handling

Tasks:
- ffmpeg error handling
- Config validation
- Deployment docs

Implemented so far:
- RTSP recording inputs use TCP transport by default
- Recording uses the primary video stream only for MP4 clips
- Full ffmpeg stderr is preserved in runtime state and logs
- Probe diagnostics distinguish input/open failure from missing video stream

### Phase 6 - Retention and Storage Protection [x]

Goals:
- Prevent recorded clips from filling the recorder host storage
- Provide visibility into recording storage usage
- Support configurable warning thresholds
- Support optional automatic cleanup of old recordings

Requirements:
- Add retention settings to app config
- Support alert-only mode
- Support optional automatic deletion mode
- Support oldest-first cleanup
- Never delete active recordings
- Only delete completed local recordings
- Log all cleanup actions
- Expose storage status in the API
- Show warnings in the UI when thresholds are exceeded

Suggested config fields:
- `retention.enabled`
- `retention.cleanup_mode`
- `retention.max_age_days`
- `retention.max_total_gb`
- `retention.minimum_free_gb`

Cleanup modes:
- `disabled`
- `alert_only`
- `delete_oldest`

API and UI behavior:
- Backend reports total recording storage usage
- Backend reports free disk space
- UI shows warning state if thresholds are exceeded
- Manual cleanup endpoint is available when retention is enabled and cleanup mode is not `disabled`
- Automatic cleanup occurs only when cleanup mode is explicitly `delete_oldest`

Implementation notes:
- Only the local recordings directory is managed
- NAS archival is out of scope
- Active recording output files are excluded from cleanup
- Cleanup deletes oldest eligible files first

## Current Implementation State

Completed:
- Phase 0 foundation
- Phase 1 dashboard and status API
- Phase 2 recording engine and recording API
- Phase 3 recording UI controls
- Phase 3A camera management UI
- Phase 4 clip management
- Phase 4B clip preview and bulk direct download
- Phase 4C optional folder-targeted clip downloads
- Phase 4A GoPro recorder support
- Phase 8 live multi-printer dashboard
- Phase 8A per-printer multi-view selector
- Phase 6 retention and storage protection

In progress:
- Phase 5 operational hardening

Note:
- Phase 6 was implemented ahead of Phase 5 operational hardening to protect recorder-host storage early.

Implemented highlights:
- FastAPI app scaffold with startup validation and logging
- JSON camera config loading with go2rtc helper mode and manual URL mode
- JSON camera config loading with go2rtc helper, manual URL, and GoPro modes
- Separate app config loading for retention settings
- Resolution logic where manual URLs override generated URLs
- Runtime camera state manager with recording metadata and error tracking
- ffmpeg recording manager with start, stop, timed capture, and one-recording-per-camera enforcement
- GoPro API recording manager with start, stop, timed record, media polling, and automatic download
- RTSP-over-TCP recording and probing defaults for `rtsp://` inputs
- Video-only MP4 recording profile using `-map 0:v:0 -an -c:v copy`
- Config-backed camera management UI with live preview/external preview and mode-aware testing
- Expanded ffmpeg and ffprobe diagnostics surfaced in the dashboard and camera management UI
- Filesystem-based clip browser with camera filter, download, and manual delete
- Inline clip preview endpoint and browser preview player on `/clips`
- Client-side bulk direct download of selected clips as individual files with no ZIP packaging
- Optional client-side chosen-folder clip saves using the browser File System Access API when available
- Browser-download fallback remains the default when folder access is unavailable, denied, or unsupported
- `/printers` live dashboard with top printer toggles, one default live view per printer, and status/details beneath each preview
- Per-printer camera/view selector on `/printers` with browser-side selection persistence and backend default fallback
- Optional Moonraker-backed status polling for printer status, file name, progress, temperatures, and ETA
- Endpoints: `GET /health`, `GET /api/cameras`, `POST /api/cameras`, `PUT /api/cameras/{camera_id}`, `DELETE /api/cameras/{camera_id}`, `POST /api/camera/probe`, `POST /api/gopro/test`, `GET /api/gopro/{camera_id}/status`, `POST /api/gopro/{camera_id}/record_for`, `POST /api/gopro/{camera_id}/download_latest`, `GET /api/gopro/{camera_id}/preview`, `GET /api/gopro/{camera_id}/media`, `GET /api/printers/cards`, `GET /api/status`, `GET /api/record/status`, `POST /api/record/start/{camera_id}`, `POST /api/record/stop/{camera_id}`, `GET /api/storage/status`, `POST /api/storage/cleanup`, `GET /api/clips`, `GET /api/clips/preview/{camera_id}/{filename}`, `GET /api/clips/download/{camera_id}/{filename}`, `DELETE /api/clips/{camera_id}/{filename}`, `GET /`, `GET /printers`, `GET /cameras`, `GET /clips`
- Dashboard camera cards with preview iframe, live status, output metadata, record controls, error display, and last recorded clip
- GoPro camera cards with start/stop, Record 30s, Download Latest, and external preview fallback
- Empty dashboard state when no cameras are configured
- Preview fallback rules: manual preview -> generated preview -> `no preview configured`
- GoPro preview modes: `none` and `external_link`; `stream_proxy` remains deferred
- Storage usage and free disk reporting in the UI
- Retention thresholds with alert-only and delete-oldest cleanup modes
- Automatic retention checks on startup and after recording completion
- Docker-first deployment with ffmpeg installed
- Docker Compose defaults that work without `.env`
- Example config files tracked in git while live deployment config files remain untracked

Next phase:
- Phase 5 operational hardening
- follow-up printer UX improvements such as clearer per-view labels or quick camera cycling

## Deployment Model

Printer NVR runs in Docker.

Host folder layout example:

```text
/opt/printer-nvr/
  docker-compose.yml
  config/
  recordings/
  logs/
```

Docker bind mounts:
- `config` -> `/app/config`
- `recordings` -> `/app/recordings`
- `logs` -> `/app/logs`
