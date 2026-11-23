from __future__ import annotations

import json
import math
import os
import re
import subprocess
from pathlib import Path

URL_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>]+")
MEDIA_SUFFIXES = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".ts"}


def publish_media(staged: Path, final: Path) -> None:
    if os.name == "nt":
        staged.rename(final)
    else:
        os.link(staged, final)
        try:
            staged.unlink()
        except OSError:
            # The published file is valid even if the private link cannot be removed.
            pass


def redact_diagnostic(message: str, source: str = "") -> str:
    if source:
        message = message.replace(source, "<input>")
    return URL_PATTERN.sub("<url>", message)


def validate_mp4(path: Path, *, run=subprocess.run) -> dict:
    if not path.is_file() or not path.stat().st_size:
        raise ValueError("FFmpeg produced no media")
    try:
        probe = run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name,width,height,avg_frame_rate:format=format_name,duration", "-of", "json", str(path)],
            capture_output=True, timeout=10, check=True,
        )
        metadata = json.loads(probe.stdout)
        stream = metadata["streams"][0]
        duration = float(metadata["format"]["duration"])
        if ("mp4" not in metadata["format"]["format_name"].split(",")
                or not math.isfinite(duration) or duration <= 0
                or stream["width"] <= 0 or stream["height"] <= 0):
            raise ValueError("Invalid video properties")
    except (subprocess.SubprocessError, OSError, KeyError, ValueError, TypeError, IndexError) as exc:
        raise ValueError("FFprobe could not verify a playable MP4 with a video stream and positive duration") from exc
    return metadata
