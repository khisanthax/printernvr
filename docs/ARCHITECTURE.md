# Printer NVR Architecture

## Scope

Printer NVR is a single-service, Docker-first application for 3D printer camera monitoring, recording, clip review, and local storage protection.

Printers are stream providers only. Recording and retention enforcement run on the central Printer NVR host.
Legacy GoPro support still exists in the codebase for backward compatibility, but it is no longer part of the active project direction.

## Runtime Components

- FastAPI web server
- Jinja template rendering
- Static assets (plain CSS and minimal JavaScript)
- JSON configuration loader for camera config and app config
- In-memory runtime camera state manager
- ffmpeg subprocess recording manager
- Moonraker status service for optional printer metadata
- Local recordings retention manager
- Config-backed camera management UI
- Compact live camera wall
- Live multi-printer dashboard
- Filesystem-based clip browser, review metadata, and preview/download/delete API
- Legacy GoPro compatibility modules retained for existing configs

## Current Module Layout

- `app/main.py`: app startup, settings, lifespan wiring, router registration
- `app/config.py`: camera config loading, app config loading, URL resolution
- `app/camera_store.py`: safe camera config CRUD and config file writes
- `app/clips.py`: recordings filesystem scan, clip metadata, secure path resolution
- `app/models.py`: Pydantic models for config, runtime state, and storage status
- `app/state.py`: runtime state manager for camera recording state
- `app/recorder.py`: ffmpeg command building, process lifecycle, monitor threads
- `app/services/gopro_service.py`: deprecated compatibility module for legacy GoPro HTTP control
- `app/services/gopro_recording_manager.py`: deprecated compatibility module for legacy GoPro jobs
- `app/retention.py`: storage scanning, threshold evaluation, cleanup planning and deletion
- `app/printers.py`: printer-card grouping and default-view selection
- `app/probe.py`: ffprobe stream testing
- `app/util.py`: logging and directory helpers
- `app/services/moonraker_service.py`: optional Moonraker status queries for printer cards
- `app/api/health.py`: health endpoint
- `app/api/dashboard.py`: dashboard page
- `templates/live.html` and `static/live.js`: compact camera wall page and browser-local wall interactions
- `app/api/cameras.py`: camera CRUD and probe API
- `GET /api/cameras/config` and `PUT /api/cameras/config`: printer-first config load/save for the nested management UI
- `app/api/gopro.py`: deprecated compatibility endpoints for legacy GoPro configs
- `app/api/status.py`: legacy runtime status API
- `app/api/record.py`: recording start, stop, and status API
- `app/api/storage.py`: storage status and manual cleanup API
- `app/api/printers.py`: live printer card status API
- `app/api/clips.py`: clip list, preview, download, and delete API

## Configuration Model

Two JSON files are used:

- `config/cameras.json`: camera definitions
- `config/app.json`: app-level settings such as retention
- `config/cameras.example.json` and `config/app.example.json`: tracked templates for new deployments

Printer-first definitions are now the preferred `config/cameras.json` shape:

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
          "display_order": 10
        }
      ]
    }
  ]
}
```

Legacy camera-first configs with top-level `cameras` still load for existing installs.
Both shapes are normalized into the same resolved camera list used by recording, clips, `/printers`, and `/live`.
Camera definitions remain the source of truth even when edited through the web UI.
The `/cameras` page writes back to `config/cameras.json` rather than introducing a database.
The management UI is now printer-first and saves top-level `printers`.
Legacy camera-first configs are still loadable and are converted to printer-first shape when saved through the nested UI.
The live `config/cameras.json` and `config/app.json` files are deployment-local and should remain untracked so host-specific edits do not block repository pulls.

Active camera modes:
- `go2rtc_helper`
- `manual_urls`

Deprecated compatibility mode:
- `gopro`

Legacy camera-to-printer mapping fields:
- `printer_id`
- `printer_name`
- `default_live_view`
- `moonraker_url`
- `display_order`

For legacy camera-first config, printers are derived from these fields.
For printer-first config, `printer.default_camera_id` is converted to the same internal default camera marker.
If printer mapping fields are omitted in legacy config, each camera falls back to its own printer card identity.

RTSP camera URL resolution:
- `record_url`: manual value, else generated go2rtc URL
- `preview_url`: manual value, else generated go2rtc preview URL, else unset

Deprecated GoPro config behavior:
- `gopro_host` identifies the legacy HERO7 target on the local network
- `preview_mode` currently supports `none` and `external_link`
- `stream_proxy` is intentionally rejected until a clean in-app preview path exists
- GoPro clips are still written into `recordings/<output_subdir>/`
- this backend remains loadable for compatibility but is not the recommended capture path

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

## Printer Dashboard Flow

1. `/printers` and `/live` build one live card per logical printer group from the same printer-card data model.
2. Cameras are grouped by `printer_id`.
3. The default live camera is chosen in this order:
- enabled cameras before disabled cameras
- `default_live_view=true` before other cameras
- cameras with preview URLs before cameras without preview URLs
- lower `display_order`
4. Each printer card exposes an `available_views` list sorted with the same default-view rules for compact selector UI.
5. Printer details are shown below the preview, not overlaid on top of video.
6. Browser-side checkbox toggles show or hide printer cards and persist visibility in `localStorage`.
7. When a printer has multiple views, the page stores the user-selected camera id in browser `localStorage` and swaps only that card's preview source.
8. If a stored camera selection is missing or no longer valid, the page falls back to the backend-computed default live view for that printer.
9. The page polls `GET /api/printers/cards` on a lightweight interval to refresh:
- status text
- file name
- progress
- extruder and bed temperatures
- ETA
10. The page also tracks per-card metadata freshness from Moonraker responses and renders relative text such as `Updated just now` or `Stale`.
11. Manual refresh remains lightweight and reuses the same polling endpoint rather than introducing websockets or a separate real-time channel.
12. Enlarged preview uses a client-side modal overlay that reuses the currently selected view for the clicked printer card.
13. Printer-card recording controls resolve the current selected `camera_id` in the browser, then call the existing camera-based `/api/record` endpoints.
14. The page polls `GET /api/record/status` and maps camera runtime state back onto the printer card for the currently selected view.
15. Each printer card shows latest clip shortcuts for the currently selected camera/view.
16. Latest clip data is discovered from the local recordings filesystem through `ClipStore.latest_clip`.
17. View changes update the live preview, recording target, clips link, and latest clip section together.
18. Recording transitions from busy to idle trigger a lightweight latest-clip refresh for the affected selected camera.
19. If a printer has `moonraker_url`, `MoonrakerService` queries it directly for status data.
20. If Moonraker is unavailable or not configured, the card still renders with:
- printer name
- selected preview
- placeholder status details

Current phase limits:
- `/printers` shows one active preview per printer card at a time
- selector state is browser-local and not stored in config
- `/live` supports one optional secondary viewing-only card per multi-camera printer, but richer multi-preview layouts remain deferred
- explicit per-view config preferences are intentionally deferred to a follow-up phase
- polling-based status refresh remains intentionally simple; no websocket or push-based monitoring path was added
- printer-card recording controls are a frontend entry point into the existing camera recording APIs, not a new recording backend
- latest clip shortcuts are read-only convenience actions over the existing clip filesystem APIs

## Camera Wall Flow

1. `/live` renders the same grouped printer cards as `/printers`, but through a compact viewing-only template.
2. The page uses the existing `/api/printers/cards` endpoint for lightweight status refresh.
3. Visibility checkboxes use a wall-specific `localStorage` key so users can choose which printers appear on the camera wall.
4. Per-printer camera/view selection reuses the same browser-side selected-view storage as `/printers`.
5. Live preview remains the dominant card area.
6. Printer status, progress, filename, temperatures, ETA, and freshness text are rendered below the video.
7. Recording controls, duration buttons, latest clip shortcuts, and clip review actions are intentionally omitted.
8. Camera wall density settings use browser `localStorage` to persist cards per row and rows per screen.
9. Fixed cards-per-row values write explicit CSS grid columns, while Auto returns to the responsive `auto-fill` layout.
10. Fixed rows-per-screen values calculate a card minimum height from the viewport height after subtracting the sticky wall header and page padding.
11. Cards whose Moonraker monitor state is `printing` are sorted before non-printing cards while preserving configured order inside each priority group.
12. Normal polling updates text, badges, freshness, and data attributes in place only.
13. Routine status refresh does not rebuild cards, replace iframes, reassign iframe `src`, or re-append card DOM nodes.
14. Printing-priority sorting uses CSS `order`, so iframe streams stay mounted unless the user changes view or the underlying preview URL/config changes.
15. `/live` uses a slower polling interval than `/printers` because it is optimized for visual monitoring rather than detailed control feedback.

Phase 10.4 secondary live-view behavior:
- `/live` can optionally show a secondary camera view for printers with two or more cameras.
- Secondary views render as separate viewing-only cards in the wall grid.
- Secondary-card preferences are browser-local and stored in `localStorage` under `printernvr-live-secondary-views`.
- Secondary cards do not add recording controls or change recording target behavior.
- `/printers` should continue to show one selected camera/view per printer because its recording controls target that selected view.
- Primary and secondary `/live` views are kept distinct; when a primary view changes to match the secondary, the frontend chooses another secondary view or hides the secondary card.
- Secondary card polling preserves iframe stability: update text/status in place and avoid rebuilding or reloading preview iframes during normal refresh.

Page roles:
- `/live`: compact dark camera wall for watching all printers
- `/printers`: detailed monitoring and recording control dashboard
- `/clips`: clip review, rename, preview, download, and delete workspace

## Recording Flow

1. Client calls `POST /api/record/start/{camera_id}` from either the camera dashboard or the selected view on a printer card.
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

Printer-card recording behavior:
- Start and Stop controls on `/printers` use the selected view's camera id.
- Quick timed controls for 10s, 15s, 20s, 30s, and 60s send `{"duration": seconds}` to the same start endpoint.
- Custom printer-card duration input validates 1-600 seconds in the browser before sending the existing timed recording payload.
- The printer card reads `GET /api/record/status` and displays the runtime state for the currently selected camera only.
- When a recording finishes, the frontend refreshes latest clip metadata for matching visible printer cards.
- Clips still land in the normal `recordings/<output_subdir>/` directory, which defaults to the camera id, and remain visible through `/clips`.

This recording profile is intentionally conservative for printer cameras:
- RTSP over TCP improves compatibility with go2rtc and camera streams that are unreliable over default transport settings
- video-only MP4 output avoids mux failures caused by audio or non-video side streams

## Deprecated GoPro Compatibility Flow

Legacy GoPro code is still present so older `mode=gopro` configs can continue to load, but this backend is no longer an active architecture target.

Current policy:
- do not expand GoPro behavior in new phases
- do not present GoPro as the recommended capture workflow
- remove the deprecated backend in a future cleanup pass once no configs depend on it

## Camera Management Flow

1. `/cameras` loads printer-first config from `GET /api/cameras/config`.
2. Browser-side form logic handles:
- id auto-generation from name
- printer create/edit/delete
- nested camera create/edit/delete
- mode-specific camera fields
- preview URL derivation for live preview
- heuristic warning when the effective recording URL looks like a browser preview stream
3. Save and delete requests update `config/cameras.json` as top-level `printers` through `CameraConfigStore`.
4. After each successful write, the running app refreshes:
- `app.state.cameras`
- `app.state.camera_index`
- runtime camera state entries
5. Printer delete and camera delete remove config entries only; local recordings and clips are not deleted.
6. Default camera selection is stored as `printer.default_camera_id`.
7. If a default camera is deleted, the config layer falls back to the first enabled camera by display/name order, or clears the default when no cameras remain.
8. RTSP stream probing uses `ffprobe` on the resolved `record_url` through `POST /api/camera/probe`.
9. If the probe input is `rtsp://`, ffprobe also uses TCP transport by default.
10. Deprecated compatibility testing for legacy GoPro configs still uses `POST /api/gopro/test`.
11. Probe results distinguish:
- input/open failure
- reachable stream with no video stream found
- reachable stream with a usable video stream

Camera management constraints:
- printer ids must be unique
- camera ids must be globally unique because recording and clips remain camera-id based
- edits are blocked while any configured camera is actively recording
- no database or server-side user preference storage is added

## Clip Browser Flow

1. `/clips` loads a lightweight template with an optional camera filter from the query string.
2. Browser-side JavaScript calls `GET /api/clips` and optionally filters by `camera_id`.
3. `ClipStore` scans the local recordings root directly from the filesystem.
4. Clip filesystem metadata includes:
- logical camera id
- filename
- relative path
- filesystem timestamp
- size
- active/in-use state
- favorite state
- rejected state
5. Review metadata is stored in a sidecar JSON file under the local recordings root.
6. Inline preview uses `GET /api/clips/preview/{camera_id}/{filename}` with safe file resolution and browser-friendly media type handling.
7. Latest clip lookup uses `GET /api/clips/latest/{camera_id}` and returns preview/download URLs for the newest completed local clip.
8. Printer cards use latest clip lookup for quick Preview, Download, and View All actions tied to the selected camera/view.
9. Download uses `GET /api/clips/download/{camera_id}/{filename}` with `FileResponse`.
10. Review updates use `PATCH /api/clips/{camera_id}/{filename}/metadata`.
11. Safe rename uses `POST /api/clips/{camera_id}/{filename}/rename` and keeps the clip inside the same camera storage directory.
12. Manual delete uses `DELETE /api/clips/{camera_id}/{filename}` and is blocked for active recording outputs.
13. Bulk direct download is handled client-side in `/clips` by iterating selected clip download URLs from one user action; the backend still validates each file request individually.
14. Optional chosen-folder saves use the browser File System Access API entirely client-side:
- the browser prompts the user to choose a directory
- the frontend may persist the directory handle in IndexedDB when the browser allows it
- the backend never receives local filesystem path data
- if folder save is unavailable or fails, the UI falls back to the existing per-file browser download flow

Clip browser safety rules:
- only paths under the local recordings root are allowed
- camera id to storage directory resolution uses current camera config when available
- path traversal is rejected
- active files are never deleted or renamed
- missing files return a clean error instead of crashing the app
- clip preview uses a separate inline-serving endpoint instead of changing the attachment behavior of the download route
- clip review metadata is local sidecar state, not a database or clip index
- bulk clip download does not generate ZIP archives or background jobs
- export/copy helpers are deferred until favorite, reject, rename, and filter workflows are fully working
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

Current deployment remains Docker-based and manual:
- clone or pull the repository
- ensure config files exist
- run `docker compose up -d --build`

Planned Phase 11 deployment direction:
- add install/update helper scripts
- add backup helper behavior for config and metadata if practical
- document common `.env` settings
- clarify volume handling for `config/`, `recordings/`, and optional `exports/`
- optionally provide a go2rtc companion container through a Compose profile, override file, or companion compose file

go2rtc deployment policy:
- external go2rtc instances remain fully supported
- bundled go2rtc must be optional
- Printer NVR must not require go2rtc to run in the same Compose stack
- setup/update helpers must not overwrite `config/cameras.json`, recordings, clip metadata, or review metadata without backup or confirmation

## Operational Notes

- App can start with zero cameras configured.
- Camera failures should set error state without crashing the app.
- Retention checks run on startup and after recording completion.
- No database, queue, scheduler, or NAS logic is included.
- GoPro support remains deprecated compatibility code, not an active architectural direction.
