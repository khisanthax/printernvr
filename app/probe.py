from __future__ import annotations

import json
import subprocess

from app.models import CameraProbeResult


def probe_record_stream(record_url: str) -> CameraProbeResult:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name,width,height,codec_type",
        "-of",
        "json",
        record_url,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except OSError as exc:
        return CameraProbeResult(
            reachable=False,
            record_url=record_url,
            error=f"Unable to run ffprobe: {exc}",
        )
    except subprocess.TimeoutExpired:
        return CameraProbeResult(
            reachable=False,
            record_url=record_url,
            error="ffprobe timed out while probing the stream",
        )

    if result.returncode != 0:
        error_message = result.stderr.strip() or result.stdout.strip() or "ffprobe failed"
        return CameraProbeResult(
            reachable=False,
            record_url=record_url,
            error=error_message,
        )

    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams", [])

    primary_stream = None
    for stream in streams:
        if stream.get("codec_type") == "video":
            primary_stream = stream
            break
    if primary_stream is None and streams:
        primary_stream = streams[0]

    return CameraProbeResult(
        reachable=True,
        record_url=record_url,
        codec=primary_stream.get("codec_name") if primary_stream else None,
        width=primary_stream.get("width") if primary_stream else None,
        height=primary_stream.get("height") if primary_stream else None,
        stream_type=primary_stream.get("codec_type") if primary_stream else None,
        streams=streams,
    )
