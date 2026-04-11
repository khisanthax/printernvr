# Printer NVR Decisions Log

This file tracks key architectural and implementation decisions that affect long-term behavior.

## 2026-03-07 - Keep Printer NVR Single-Service and Docker-First

Decision:
- Use a single FastAPI service with Docker Compose as the default deployment path.

Why:
- Keeps deployment simple and operational overhead low.
- Matches project scope as a focused self-hosted tool.

Impact:
- No database or distributed components in MVP.
- ffmpeg recording lifecycle will run in this same service process.

## 2026-03-07 - Camera Config Supports Helper and Manual Modes

Decision:
- Support both go2rtc helper mode and manual URL mode.
- Manual URLs override generated helper URLs.

Why:
- Most printers expose go2rtc streams, but the app must remain a generic stream consumer.

Impact:
- Config parser resolves final URLs at startup.
- Camera configuration remains JSON and user-editable.

## 2026-03-07 - Preview Fallback Must Not Use RTSP Record URL

Decision:
- Preview resolution order:
1. manual `preview_url`
2. go2rtc generated preview URL
3. no preview configured
- Do not fall back to `record_url` for browser preview.

Why:
- Browser preview via iframe generally cannot render RTSP.
- Avoids broken preview assumptions in UI.

Impact:
- Dashboard renders an explicit `no preview configured` placeholder.

## 2026-03-07 - Zero Cameras Must Not Block Startup

Decision:
- App starts successfully even when camera list is empty.

Why:
- Supports first-time deployment and iterative configuration.

Impact:
- Dashboard shows an empty-state message: `No cameras configured.`

## 2026-03-07 - Docker Compose Must Work Without .env

Decision:
- Remove hard dependency on `.env` in Compose.
- Provide Compose defaults and optional `.env.example`.

Why:
- `docker compose up -d --build` should work out-of-the-box.

Impact:
- Optional `.env` can override defaults later.
- `LOG_LEVEL` and `PORT` remain configurable without breaking default startup.

## 2026-03-07 - Use Separate App Config for Retention Settings

Decision:
- Keep camera config in `config/cameras.json`.
- Store retention settings in `config/app.json`.

Why:
- Retention is an app-level concern, not a per-camera setting.
- This matches the stated preference for app config plus camera config without introducing a database.

Impact:
- Startup now loads both camera config and app config.
- Default app config can safely disable retention.

## 2026-03-07 - Use ffmpeg Subprocesses with In-Memory Process Tracking

Decision:
- Implement recording with direct `ffmpeg` subprocesses managed by a `RecordingManager`.
- Track one active process per camera in memory.

Why:
- Keeps the service single-process and easy to operate.
- Fits the project rule set for using ffmpeg directly rather than adding workers or queues.

Impact:
- Timed recordings are implemented by passing `-t` to ffmpeg.
- Runtime state is the source of truth for active outputs and UI status.

## 2026-03-07 - Retention Must Exclude Active Recording Outputs

Decision:
- Cleanup logic excludes active recording output paths from deletion planning.
- Cleanup only scans the local recordings root.

Why:
- Active output deletion would corrupt recordings and create hard-to-debug failures.
- NAS or external archival remains explicitly out of scope.

Impact:
- Retention depends on runtime recording state.
- Automatic and manual cleanup only affect completed local files.

## 2026-03-07 - Alert-Only and Delete-Oldest Are Both Supported

Decision:
- Support three cleanup modes: `disabled`, `alert_only`, and `delete_oldest`.

Why:
- Some deployments need visibility without automatic deletion.
- Other deployments need the recorder host protected automatically.

Impact:
- Warning status is exposed in API/UI even when automatic deletion is off.
- Manual cleanup is available when retention is enabled and mode is not `disabled`.

## 2026-03-07 - Camera Management Remains Config-File Based

Decision:
- Add camera management through the web UI, but keep `config/cameras.json` as the source of truth.
- Do not add a database.

Why:
- The project is intended to stay simple, portable, and easy to self-host.
- Camera configuration is small enough to manage safely in JSON.

Impact:
- Camera create, update, and delete operations write back to the JSON config file.
- The running app refreshes in-memory camera state after successful writes.

## 2026-03-07 - Block Camera Edit/Delete While Recording

Decision:
- Prevent editing or deleting a camera that is actively recording.

Why:
- Changing camera identity or removing a configured camera during an active ffmpeg process risks inconsistent state.

Impact:
- Users must stop the recording first, then edit or delete the camera.
- Deletion only removes config; it does not delete recordings.

## 2026-03-07 - Clip Browser Reads Directly from the Filesystem

Decision:
- Implement clip browsing, download, and manual deletion by scanning the local recordings root directly.
- Do not add a database or clip index.

Why:
- Recordings already exist as files on disk under per-camera directories.
- A direct filesystem scan keeps the feature simple and consistent with the rest of the project.

Impact:
- `/clips` reflects the current local recordings directory without extra synchronization.
- Clip metadata is derived from filesystem state and timestamps.
- Secure path resolution and active-file protection are required in the API layer.

## 2026-03-07 - Use RTSP-over-TCP and Video-Only MP4 Recording by Default

Decision:
- For `rtsp://` recording and probe inputs, use TCP transport by default.
- Record only the primary video stream into MP4 clips.

Why:
- Several camera and go2rtc streams open more reliably over RTSP/TCP.
- Copying all streams into MP4 can fail when the input exposes audio or other side streams that do not mux cleanly.

Impact:
- Default ffmpeg recording uses `-rtsp_transport tcp`, `-map 0:v:0`, `-an`, and `-c:v copy` for RTSP printer streams.
- Working cameras keep stream-copy performance while problematic cameras avoid common MP4 conversion failures.
- Full ffmpeg stderr and command details are preserved in runtime state for troubleshooting.

## 2026-03-08 - Treat GoPro as a Separate Recorder Backend

Decision:
- Add GoPro support as a separate `mode=gopro` camera backend.
- Do not force GoPro recording through ffmpeg input capture.

Why:
- GoPro recording quality is a separate use case from printer IP streams.
- HERO7 recording is more reliable when controlled through the device API and downloaded after stop.

Impact:
- Shared runtime state and `/api/record` dispatch now cover both ffmpeg and GoPro backends.
- GoPro clips still land in the same local recordings tree and appear in the existing clip browser.
- Preview support for GoPro remains best-effort and external-link based in v1.

## 2026-03-09 - Keep Bulk Clip Download Client-Side and Per-File

Decision:
- Add clip preview through a dedicated inline-serving endpoint.
- Implement bulk clip download in the browser by triggering the existing per-file download endpoint for each selected clip.
- Do not add ZIP packaging.

Why:
- The project should stay filesystem-based and operationally simple.
- Per-file downloads preserve the current secure path validation model and avoid adding archive generation work on the server.

Impact:
- `/clips` now supports inline preview and one-click multi-download from a single user action.
- Browsers may still prompt for permission before allowing multiple downloads.
- Existing single download and delete semantics remain unchanged.

## 2026-03-09 - Keep Optional Folder-Targeted Downloads Client-Side Only

Decision:
- Add optional chosen-folder clip downloads through the browser File System Access API.
- Keep folder-handle storage in the browser only.
- Fall back to normal browser downloads whenever support, permission, or direct-save fails.

Why:
- The feature should improve usability without changing the backend security model or adding server-side path awareness.
- Browser APIs already enforce the correct user-granted permission boundary.

Impact:
- `/clips` can save directly into a user-selected folder in supporting browsers.
- No backend local-path tracking, no database storage, and no ZIP packaging were added.
- Folder-handle persistence is browser-dependent and remains optional.

## 2026-04-11 - Derive Live Printer Cards from Camera Config

Decision:
- Add a dedicated `/printers` live page that groups cameras into printer cards using lightweight camera config fields.
- Keep one default live camera per printer in this phase.
- Show printer status/details below the preview rather than overlaying them on video.

Why:
- The live monitoring page needs printer grouping without introducing a database or a second config system.
- A single default live view keeps the first implementation practical while leaving room for a later multi-view selector.

Impact:
- Camera config now supports `printer_id`, `printer_name`, `default_live_view`, `moonraker_url`, and `display_order`.
- `/printers` can optionally enrich cards with Moonraker status, progress, temperatures, and ETA.
- Multi-view/camera switching per printer is intentionally deferred to a follow-up phase.

## 2026-04-11 - Keep Per-Printer View Selection Browser-Side

Decision:
- Add a per-printer camera/view selector on `/printers` when a printer has multiple configured views.
- Persist the selected camera id in browser `localStorage` only.
- Keep backend `default_live_view` logic as the fallback whenever the stored selection is missing or invalid.

Why:
- The live dashboard needs quick camera switching without introducing a database or per-user server-side preference storage.
- Browser-local persistence keeps the feature lightweight and avoids changing the config source of truth for each temporary view choice.

Impact:
- `GET /api/printers/cards` now exposes selector-ready `available_views` data per printer card.
- The frontend swaps only the selected card preview without changing printer-level Moonraker metadata.
- If camera config changes invalidate a stored selection, the dashboard falls back cleanly to the backend default camera.

## 2026-04-11 - Keep Printer Monitoring Polish Polling-Based and Card-Local

Decision:
- Add enlarged preview, state badges, freshness text, and manual refresh controls to `/printers`.
- Reuse the existing polling endpoint and keep the implementation card-local and browser-driven.

Why:
- The live dashboard needs better monitoring ergonomics, but the project still needs to avoid websocket infrastructure, a database, or a SPA rewrite.
- Card-local degraded states ensure one broken printer or preview does not affect the rest of the monitoring grid.

Impact:
- `/printers` now provides a modal enlarged-view experience without replacing the card grid.
- Printer status is normalized into a small badge vocabulary for clearer scanning.
- Metadata freshness is shown from Moonraker polling timestamps, while printers without metadata sources stay readable with explicit fallback text.
