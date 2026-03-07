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
