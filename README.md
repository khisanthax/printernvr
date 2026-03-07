# Printer NVR

Printer NVR is a lightweight, Docker-first web app for monitoring and recording 3D printer cameras.

It is intentionally scoped to 3D printer workflows, not general CCTV management.

## Phase Coverage

This repository currently includes:
- Phase 0 foundation (Docker, config loading, validation, health, base dashboard)
- Phase 1 dashboard features (camera cards, runtime status API, control placeholders)

Recording controls are present in the UI but recording is not implemented until Phase 2.

## Project Structure

```text
app/            FastAPI backend modules
config/         Camera configuration JSON
recordings/     Output clips (bind mount)
logs/           Application logs (bind mount)
templates/      HTML templates
static/         CSS/JS assets
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

4. Create config file from example (or edit the default `config/cameras.json`):

```bash
cp config/cameras.example.json config/cameras.json
```

5. Run the server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8787 --reload
```

Open `http://localhost:8787`.

## Docker Run Instructions

1. Ensure `config/cameras.json` exists.
2. Choose one option:

```bash
# Option A (recommended)
cp .env.example .env
```

```bash
# Option B
# Skip creating .env and use built-in defaults
```

3. Build and start:

```bash
docker compose up -d --build
```

The app is available at `http://localhost:8787` by default.
If `PORT` is set in `.env`, Docker Compose uses that host port.

## Environment Variables

From `.env` (optional):

- `PORT` default: `8787`
- `LOG_LEVEL` default: `info`

- `APP_CONFIG_PATH` default: `/app/config/cameras.json`
- `APP_RECORDINGS_DIR` default: `/app/recordings`
- `APP_LOGS_DIR` default: `/app/logs`
- `APP_LOG_LEVEL` default: unset (falls back to `LOG_LEVEL`)

## Camera Configuration

Camera config is JSON at `config/cameras.json`.

Top-level object format:

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

Final URL resolution order:
1. Manual `preview_url`
2. go2rtc-generated preview URL
3. Dashboard shows `no preview configured`

For recording URL:
1. Manual `record_url`
2. go2rtc-generated record URL

Manual URLs always override generated values.

### Supported Camera Fields

- `id` (required)
- `name` (required)
- `enabled` (default `true`)
- `description` (optional)
- `go2rtc_base_url` (helper mode)
- `stream_name` (helper mode, default `cam`)
- `preview_url` (manual mode)
- `record_url` (manual mode)
- `output_subdir` (defaults to `id`)

## API Endpoints

- `GET /health` basic health and loaded camera count
- `GET /api/cameras` resolved camera configuration
- `GET /api/status` runtime camera state map

## Notes

- ffmpeg is installed in the Docker image for Phase 2 recording.
- NAS sync is intentionally out of scope for application logic.
- Startup validates config structure and resolved URLs while allowing zero cameras.
