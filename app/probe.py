from __future__ import annotations

import json
import logging
import subprocess
from subprocess import list2cmdline

from app.models import CameraProbeResult

LOGGER = logging.getLogger(__name__)


def probe_record_stream(record_url: str) -> CameraProbeResult:
    command = ["ffprobe"]
    if record_url.lower().startswith("rtsp://"):
        command.extend(["-rtsp_transport", "tcp"])
    command.extend(
        [
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,width,height,codec_type",
            "-of",
            "json",
            record_url,
        ]
    )

    command_text = list2cmdline(command)

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
        LOGGER.warning("ffprobe execution failed for %s: %s", record_url, exc)
        return CameraProbeResult(
            reachable=False,
            record_url=record_url,
            diagnostic_status="input_open_failure",
            message="Unable to run ffprobe",
            error=f"Unable to run ffprobe: {exc}",
            details=str(exc),
            command=command_text,
        )
    except subprocess.TimeoutExpired:
        LOGGER.warning("ffprobe timed out for %s", record_url)
        return CameraProbeResult(
            reachable=False,
            record_url=record_url,
            diagnostic_status="input_open_failure",
            message="ffprobe timed out while probing the stream",
            error="ffprobe timed out while probing the stream",
            details="ffprobe exceeded the 15 second timeout while opening the input.",
            command=command_text,
        )

    if result.returncode != 0:
        error_message = result.stderr.strip() or result.stdout.strip() or "ffprobe failed"
        LOGGER.warning(
            "ffprobe input failure for %s\ncommand: %s\nstderr:\n%s",
            record_url,
            command_text,
            error_message,
        )
        return CameraProbeResult(
            reachable=False,
            record_url=record_url,
            diagnostic_status="input_open_failure",
            message="ffprobe could not open the input stream",
            error=error_message,
            details=error_message,
            command=command_text,
        )

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        LOGGER.warning(
            "ffprobe returned invalid JSON for %s\ncommand: %s\nstdout:\n%s",
            record_url,
            command_text,
            result.stdout,
        )
        return CameraProbeResult(
            reachable=False,
            record_url=record_url,
            diagnostic_status="input_open_failure",
            message="ffprobe returned unreadable output",
            error=f"ffprobe output parse failed: {exc}",
            details=result.stdout.strip() or None,
            command=command_text,
        )
    streams = payload.get("streams", [])

    primary_stream = None
    for stream in streams:
        if stream.get("codec_type") == "video":
            primary_stream = stream
            break
    if primary_stream is None and streams:
        primary_stream = streams[0]

    if primary_stream is None or primary_stream.get("codec_type") != "video":
        LOGGER.info("ffprobe found no video stream for %s", record_url)
        return CameraProbeResult(
            reachable=True,
            record_url=record_url,
            diagnostic_status="no_video_stream",
            message="Stream opened, but no video stream was found",
            error="No video stream found in ffprobe output",
            details=result.stdout.strip() or None,
            command=command_text,
            streams=streams,
        )

    LOGGER.info(
        "ffprobe found video stream for %s (codec=%s, %sx%s)",
        record_url,
        primary_stream.get("codec_name"),
        primary_stream.get("width"),
        primary_stream.get("height"),
    )
    return CameraProbeResult(
        reachable=True,
        record_url=record_url,
        diagnostic_status="ok",
        message="ffprobe opened the stream and found a video stream",
        codec=primary_stream.get("codec_name") if primary_stream else None,
        width=primary_stream.get("width") if primary_stream else None,
        height=primary_stream.get("height") if primary_stream else None,
        stream_type=primary_stream.get("codec_type") if primary_stream else None,
        video_stream_found=True,
        command=command_text,
        streams=streams,
    )
