# Printer NVR Roadmap

This document tracks the implementation roadmap for **Printer NVR** and serves as the working reference for phased development.

## Project Overview

Printer NVR is a lightweight web-based recording system for multiple 3D printer cameras.

Each printer exposes one or more camera streams, typically through go2rtc or direct RTSP/manual URLs. Printer NVR provides a web UI where users can monitor printers, record short clips, and review those clips for downstream social-media use.

Users should be able to:
- View multiple printer camera streams
- Start recording manually
- Stop recording manually
- Record for a fixed duration that stops automatically
- Use a compact live camera wall for watching all printers at once

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

Printer NVR actively supports two camera configuration modes.

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

### Legacy Compatibility: GoPro API-controlled recording

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

Legacy GoPro cameras:
- do not record through ffmpeg
- are controlled through the GoPro HTTP API
- download clips back into the normal local recordings directory after stop
- may use an external preview link when in-app live preview is not practical

This backend is no longer part of the active project direction. It remains in the codebase only for backward compatibility until a dedicated cleanup pass removes it safely.

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

Active project direction:
- RTSP/go2rtc and manual URL camera capture
- live multi-printer monitoring
- filesystem-based clip review and export workflow

Deprecated compatibility:
- GoPro capture remains loadable in the codebase but is no longer a planned expansion path

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

### Legacy Compatibility - GoPro Recorder Support [deprecated]

Status:
- Retained only for backward compatibility
- Not part of the active roadmap
- Not the recommended capture workflow for current deployments

Compatibility scope already present in code:
- `mode=gopro` config parsing
- GoPro connectivity testing
- GoPro start/stop/timed-record/download API routes
- in-process GoPro recording manager
- external preview fallback

Cleanup note:
- Remove deprecated GoPro backend once no deployments depend on `mode=gopro`

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

### Phase 8B - Printer Dashboard Monitoring Polish [x]

Goals:
- Improve day-to-day monitoring usability on `/printers`
- Make printer state, freshness, and degraded conditions easier to read
- Add a lightweight enlarged live-view experience without changing the page architecture

Tasks:
- Add enlarged preview modal for the currently selected printer view
- Improve printer state badges
- Add per-card last-updated freshness text
- Add lightweight refresh controls
- Improve offline and preview-unavailable states without breaking card layout

Deliverables:
- Enlarged live preview modal on `/printers`
- Clear printer-state badges for printing, idle, complete, paused, error, offline, and unavailable
- Per-card freshness text such as `Updated just now` or `Stale`
- Page-level and per-card refresh controls

### Phase 8C - Recording Controls on Printer Cards [x]

Goals:
- Make `/printers` the main watch-and-capture dashboard
- Start and stop recording from each printer card
- Record a one-click 30-second clip from the selected printer view
- Keep recording controls below the preview and tied to the selected camera/view

Tasks:
- Add compact Start, Stop, and Record 30s controls to printer cards
- Resolve the selected camera id from the current per-printer view selector
- Reuse the existing `/api/record` start, stop, and status endpoints
- Show per-card recording state and local action errors
- Keep clip storage and `/clips` behavior unchanged

Deliverables:
- Printer-card recording controls on `/printers`
- Selected-view recording targeting for grouped printers
- Per-card runtime recording state for idle, starting, recording, stopping, downloading, and error
- Direct link from each printer card to clips for the selected camera

### Phase 8D / 8.4 - Clip Shortcuts and Latest Clip Preview on Printer Cards [x]

Goals:
- Tighten the watch, record, review workflow on `/printers`
- Show latest clip information for the currently selected camera/view
- Provide quick latest-clip preview, download, and view-all actions from each printer card

Tasks:
- Add latest clip metadata to printer card and view-option models
- Add `GET /api/clips/latest/{camera_id}` using the existing filesystem clip store
- Add compact latest clip UI below printer-card recording controls
- Refresh latest clip data when the selected view changes and after recording finishes
- Add a lightweight latest clip preview modal using the existing clip preview endpoint

Deliverables:
- Latest clip shortcuts on `/printers`
- Latest clip state follows the currently selected camera/view
- Preview Latest, Download Latest, and View All Clips actions on printer cards
- Filesystem-based clip discovery reused from the clip browser

### Phase 8E / 8.5 - Custom Recording Durations on Printer Cards [x]

Goals:
- Add flexible short-clip recording durations directly to printer cards
- Keep timed recording actions tied to the currently selected camera/view
- Support both common social-media clip lengths and custom seconds

Tasks:
- Add compact 10s, 15s, 20s, 30s, and 60s duration buttons to printer cards
- Add a per-card custom duration input with browser-side validation
- Reuse the existing timed `/api/record/start/{camera_id}` payload
- Keep recording buttons disabled while the selected camera is busy
- Refresh latest clip metadata after timed recording finishes

Deliverables:
- Quick timed recording buttons on `/printers`
- Custom 1-600 second recording input per printer card
- Existing camera recording backends reused without a new subsystem

### Phase 9 - Clip Review and Social Export Polish [x]

Goals:
- Improve the `/clips` review workflow for choosing short clips for social media
- Track clip review state without adding a database
- Preserve existing clip preview, download, bulk download, folder-targeted download, and delete behavior

Scope:
- Filesystem-based clip metadata using sidecar JSON
- Mark clips as favorites/keepers
- Mark clips as rejected without deleting them
- Filter clips by favorite/rejected state
- Filter clips by camera and filename/search text
- Safely rename completed clips from `/clips`
- No database
- No ZIP downloads
- No export/copy helper until favorite, reject, rename, and filter workflows are fully working

Deliverables:
- Favorite and rejected state visible in `/clips`
- Review filters for all, favorites, rejected, and kept clips
- Search filter for clip filename, camera id, and relative path
- Safe rename action that keeps clips inside the same recordings folder
- Sidecar metadata stored locally under the recordings root

Metadata behavior:
- Review metadata is stored in a local sidecar JSON file under the recordings root
- Metadata tracks non-destructive review state such as favorite/keeper and rejected
- Rename stays inside the same camera recordings folder and follows safe filesystem rules
- Metadata remains local to the app and filesystem-based

Safety constraints:
- No path traversal
- No unsafe rename
- No silent overwrite
- No database
- No ZIP packaging
- Rejected clips are not deleted automatically
- Existing clips remain normal files under `recordings/<camera_id>/`

Validation:
- `python -m compileall app`
- `node --check static\\clips.js`
- `git diff --check`

### Phase 9.1 - Clip Review Quality-of-Life [ ]

Possible follow-up items:
- Download Favorites
- Select all visible clips
- Clear selection
- Hide rejected by default, if not already done
- Rename latest clip shortcut from `/printers`
- Better camera, printer, and date filters
- Optional export-folder copy workflow, still no ZIP

### Phase 10 - Camera Wall Live View [x]

Goals:
- Add a separate compact `/live` page for watching all printer cameras at once
- Keep `/printers` as the detailed monitoring and recording control dashboard
- Use a dark Klipper-style card grid with live preview as the dominant element
- Keep printer status and details below the video, never overlaid on the preview

Tasks:
- Add `/live` route and template
- Reuse the existing printer card grouping and available-view data model
- Add compact visibility checkboxes with browser-side persistence
- Add compact per-printer camera/view selector when multiple views exist
- Poll the existing printer cards API for lightweight status refresh
- Scope dark camera-wall styling to the `/live` page

Deliverables:
- `/live` camera wall page
- Dark compact card grid optimized for live viewing
- Printer visibility toggles persisted in `localStorage`
- Per-printer selected view persistence shared with the existing printer dashboard
- Status, file, progress, temperature, and ETA details below each preview
- No recording controls, duration buttons, latest clip panels, or review controls on `/live`

Future follow-up ideas:
- Fullscreen camera wall mode
- Drag/drop card ordering
- Per-printer multi-view selector refinements
- More compact mobile layout

### Phase 10.1 - Configurable Camera Wall Grid Density [x]

Goals:
- Let users tune how many `/live` cards fit across the wall
- Let users tune how many card rows fit in the visible browser window
- Keep `/live` viewing-focused and separate from `/printers`
- Move actively printing printers ahead of idle, complete, offline, or unavailable cards

Tasks:
- Add compact Cards per row and Rows per screen controls to `/live`
- Persist density settings in browser `localStorage`
- Apply fixed columns for 2, 3, or 4 cards per row, with Auto preserving responsive behavior
- Calculate card minimum height from viewport height for 1, 2, or 3 rows per screen
- Recalculate layout on page load, setting change, and browser resize
- Sort printing printers to the front of the camera wall while preserving configured order within each group

Deliverables:
- Configurable camera wall density on `/live`
- Browser-persisted layout settings under `printernvr-live-layout`
- Printing printers prioritized into the first visible grid positions
- Existing visibility toggles, view selectors, and status refresh preserved

### Phase 10.2 - Printer-First Configuration Model and Live Wall Refresh Stability [x]

Goals:
- Support printers as the preferred configuration root, with multiple camera views nested under each printer
- Preserve legacy camera-first config loading for existing installs
- Keep recording and clips camera-id based internally
- Stabilize `/live` polling so camera iframes are not reloaded during normal status refreshes

Tasks:
- Add printer-first config models for printers and nested camera views
- Normalize printer-first and legacy camera-first config into the existing resolved camera runtime model
- Preserve printer-first config shape on camera management writes when the file already uses `printers`
- Update the example camera config to show one printer with multiple cameras
- Increase `/live` polling interval and update only text/status/freshness fields during normal polling
- Sort printing cards with CSS `order` only, without moving or re-rendering card DOM nodes

Deliverables:
- Preferred `config/cameras.json` shape now supports top-level `printers`
- Existing top-level `cameras` configs still load
- `/live` avoids iframe reloads unless the selected camera/view or preview URL actually changes
- Recording remains through `/api/record/*/{camera_id}`
- Clips remain under `recordings/<camera_id>/`

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
- Phase 8 live multi-printer dashboard
- Phase 8A per-printer multi-view selector
- Phase 8B printer dashboard monitoring polish
- Phase 8C printer card recording controls
- Phase 8D printer card latest clip shortcuts
- Phase 8E printer card custom recording durations
- Phase 9 clip review and social export polish
- Phase 10 camera wall live view
- Phase 10.1 configurable camera wall grid density
- Phase 10.2 printer-first config and live wall refresh stability
- Phase 6 retention and storage protection

In progress:
- Phase 5 operational hardening

Note:
- Phase 6 was implemented ahead of Phase 5 operational hardening to protect recorder-host storage early.

Implemented highlights:
- FastAPI app scaffold with startup validation and logging
- JSON camera config loading with go2rtc helper and manual URL modes
- Printer-first config loading with legacy camera-first compatibility
- Legacy compatibility remains for existing `mode=gopro` configs, but GoPro is no longer an active roadmap direction
- Separate app config loading for retention settings
- Resolution logic where manual URLs override generated URLs
- Runtime camera state manager with recording metadata and error tracking
- ffmpeg recording manager with start, stop, timed capture, and one-recording-per-camera enforcement
- RTSP-over-TCP recording and probing defaults for `rtsp://` inputs
- Video-only MP4 recording profile using `-map 0:v:0 -an -c:v copy`
- Config-backed camera management UI with live preview/external preview and mode-aware testing
- Expanded ffmpeg and ffprobe diagnostics surfaced in the dashboard and camera management UI
- Filesystem-based clip browser with camera filter, download, and manual delete
- Filesystem-based clip review metadata for favorite/rejected state and safe clip rename
- Inline clip preview endpoint and browser preview player on `/clips`
- Client-side bulk direct download of selected clips as individual files with no ZIP packaging
- Optional client-side chosen-folder clip saves using the browser File System Access API when available
- Browser-download fallback remains the default when folder access is unavailable, denied, or unsupported
- `/printers` live dashboard with top printer toggles, one default live view per printer, and status/details beneath each preview
- `/live` camera wall with compact dark cards, visibility toggles, optional view selectors, and status/details beneath each preview
- `/live` density controls for cards per row and rows per screen, with browser-persisted settings and printing-printer priority sorting
- `/live` polling updates status text in place, uses CSS ordering only, and avoids reloading camera iframes during normal refreshes
- Per-printer camera/view selector on `/printers` with browser-side selection persistence and backend default fallback
- Enlarged preview modal, printer-state badges, degraded-state placeholders, freshness text, and lightweight manual refresh controls on `/printers`
- Printer-card Start, Stop, quick duration, and custom duration controls that target the currently selected camera/view and reuse the existing camera recording APIs
- Printer-card latest clip shortcuts that preview, download, or open clips for the currently selected camera/view
- Printer-card quick duration buttons and custom duration input for selected-view timed recordings
- Optional Moonraker-backed status polling for printer status, file name, progress, temperatures, and ETA
- Endpoints: `GET /health`, `GET /api/cameras`, `POST /api/cameras`, `PUT /api/cameras/{camera_id}`, `DELETE /api/cameras/{camera_id}`, `POST /api/camera/probe`, `GET /api/printers/cards`, `GET /api/status`, `GET /api/record/status`, `POST /api/record/start/{camera_id}`, `POST /api/record/stop/{camera_id}`, `GET /api/storage/status`, `POST /api/storage/cleanup`, `GET /api/clips`, `GET /api/clips/latest/{camera_id}`, `PATCH /api/clips/{camera_id}/{filename}/metadata`, `POST /api/clips/{camera_id}/{filename}/rename`, `GET /api/clips/preview/{camera_id}/{filename}`, `GET /api/clips/download/{camera_id}/{filename}`, `DELETE /api/clips/{camera_id}/{filename}`, `GET /`, `GET /live`, `GET /printers`, `GET /cameras`, `GET /clips`
- Legacy compatibility endpoints remain for existing GoPro deployments but are deprecated and not part of the active workflow
- Dashboard camera cards with preview iframe, live status, output metadata, record controls, error display, and last recorded clip
- Empty dashboard state when no cameras are configured
- Preview fallback rules: manual preview -> generated preview -> `no preview configured`
- Storage usage and free disk reporting in the UI
- Retention thresholds with alert-only and delete-oldest cleanup modes
- Automatic retention checks on startup and after recording completion
- Docker-first deployment with ffmpeg installed
- Docker Compose defaults that work without `.env`
- Example config files tracked in git while live deployment config files remain untracked

Next phase:
- Phase 5 operational hardening
- Phase 9.1 clip review quality-of-life
- Phase 10 follow-ups such as fullscreen wall mode, drag/drop ordering, and additional compact mobile refinements

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
