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

Printer NVR supports two camera configuration modes.

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
- `go2rtc_base_url`
- `stream_name`
- `preview_url`
- `record_url`
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
- Phase 6 retention and storage protection

In progress:
- Phase 5 operational hardening

Note:
- Phase 6 was implemented ahead of Phase 5 operational hardening to protect recorder-host storage early.

Implemented highlights:
- FastAPI app scaffold with startup validation and logging
- JSON camera config loading with go2rtc helper mode and manual URL mode
- Separate app config loading for retention settings
- Resolution logic where manual URLs override generated URLs
- Runtime camera state manager with recording metadata and error tracking
- ffmpeg recording manager with start, stop, timed capture, and one-recording-per-camera enforcement
- RTSP-over-TCP recording and probing defaults for `rtsp://` inputs
- Video-only MP4 recording profile using `-map 0:v:0 -an -c:v copy`
- Config-backed camera management UI with live preview and ffprobe testing
- Expanded ffmpeg and ffprobe diagnostics surfaced in the dashboard and camera management UI
- Filesystem-based clip browser with camera filter, download, and manual delete
- Endpoints: `GET /health`, `GET /api/cameras`, `POST /api/cameras`, `PUT /api/cameras/{camera_id}`, `DELETE /api/cameras/{camera_id}`, `POST /api/camera/probe`, `GET /api/status`, `GET /api/record/status`, `POST /api/record/start/{camera_id}`, `POST /api/record/stop/{camera_id}`, `GET /api/storage/status`, `POST /api/storage/cleanup`, `GET /api/clips`, `GET /api/clips/download/{camera_id}/{filename}`, `DELETE /api/clips/{camera_id}/{filename}`, `GET /`, `GET /cameras`, `GET /clips`
- Dashboard camera cards with preview iframe, live status, output metadata, record controls, error display, and last recorded clip
- Empty dashboard state when no cameras are configured
- Preview fallback rules: manual preview -> generated preview -> `no preview configured`
- Storage usage and free disk reporting in the UI
- Retention thresholds with alert-only and delete-oldest cleanup modes
- Automatic retention checks on startup and after recording completion
- Docker-first deployment with ffmpeg installed
- Docker Compose defaults that work without `.env`

Next phase:
- Phase 5 operational hardening

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
