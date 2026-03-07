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

### Phase 2 - Recording Engine [ ]

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

### Phase 3 - UI Controls [ ]

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

### Phase 4 - Clip Management [ ]

Goals:
- View recorded clips
- Download clips

Tasks:
- File listing
- Metadata display
- Download links
- Optional delete

### Phase 5 - Operational Hardening [ ]

Goals:
- Reliability
- Logging
- Startup checks
- Camera failure handling

Tasks:
- ffmpeg error handling
- Config validation
- Deployment docs

## Current Implementation State

Completed:
- Phase 0 foundation
- Phase 1 dashboard and status API

Implemented highlights:
- FastAPI app scaffold with startup validation and logging
- JSON camera config loading with go2rtc helper mode and manual URL mode
- Resolution logic where manual URLs override generated URLs
- Runtime camera state manager with initial `idle` status
- Endpoints: `GET /health`, `GET /api/cameras`, `GET /api/status`, `GET /`
- Dashboard camera cards with preview iframe, status badge, output directory, and placeholder controls
- Empty dashboard state when no cameras are configured
- Preview fallback rules: manual preview -> generated preview -> `no preview configured`
- Docker-first deployment with ffmpeg installed
- Docker Compose defaults that work without `.env`

Next phase:
- Phase 2 recording engine (ffmpeg subprocess lifecycle and recording API)

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
