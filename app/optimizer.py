from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from app.media import publish_media, validate_mp4


class Optimizer:
    def __init__(self):
        self._lock = Lock()
        self._state = {"status": "idle"}
        self._source: Path | None = None

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def active_paths(self) -> set[str]:
        with self._lock:
            return {str(self._source)} if self._source and self._state["status"] == "running" else set()

    def start(self, source: Path, reserve: int, crf: int, store, camera_id: str) -> None:
        if crf not in {20, 22, 23}:
            raise ValueError("Choose H.264 CRF 20, 22, or 23")
        size = source.stat().st_size
        if shutil.disk_usage(source.parent).free < reserve + size:
            raise ValueError("Insufficient free space for a separate optimized copy")
        with self._lock:
            if self._state["status"] == "running":
                raise ValueError("An optimization is already running")
            self._state = {"status": "running", "filename": source.name, "original_bytes": size, "crf": crf}
            self._source = source
            worker = Thread(target=self._encode, args=(source, reserve, crf, store, camera_id), daemon=True)
            try:
                worker.start()
            except RuntimeError:
                self._state["status"] = "error"
                raise

    def _encode(self, source: Path, reserve: int, crf: int, store, camera_id: str) -> None:
        started = time.monotonic()
        job_id = uuid4().hex
        final = source.with_name(f"{source.stem[:100]}_optimized_{job_id[:8]}.mp4")
        staged = final.with_suffix(".mp4.part")
        outcome = {"status": "error"}
        try:
            original = source.stat()
            reference = validate_mp4(source)
            with subprocess.Popen(
                ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-map", "0:v:0", "-an",
                 "-c:v", "libx264", "-preset", "fast", "-threads", "2", "-crf", str(crf),
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-n", "-f", "mp4", str(staged)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ) as encoder:
                while encoder.poll() is None:
                    if shutil.disk_usage(source.parent).free < reserve or time.monotonic() - started > 1800:
                        encoder.kill()
                        raise ValueError("Optimization stopped at the disk or runtime limit")
                    time.sleep(0.25)
                if encoder.returncode:
                    raise ValueError("FFmpeg failed to encode this clip")
            candidate = validate_mp4(staged)
            subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(staged), "-map", "0:v:0",
                 "-f", "null", "-"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=True, timeout=1800,
            )
            expected, actual = reference["streams"][0], candidate["streams"][0]
            for key in ("width", "height"):
                if expected[key] != actual[key]:
                    raise ValueError("The optimized copy changed video dimensions")
            duration = float(reference["format"]["duration"])
            if abs(duration - float(candidate["format"]["duration"])) > max(0.15, duration * 0.01):
                raise ValueError("The optimized copy changed video duration")
            size = staged.stat().st_size
            saved = 1 - size / original.st_size
            outcome.update(optimized_bytes=size, savings_percent=round(saved * 100, 2))
            if saved < 0.2:
                outcome.update(status="skipped", message="Candidate did not save at least 20%")
            else:
                with store._review_lock:
                    current = source.stat()
                    if (current.st_size, current.st_mtime_ns) != (original.st_size, original.st_mtime_ns):
                        raise ValueError("The original clip changed during optimization")
                    review = store._load_metadata(strict=True).get(f"{camera_id}::{source.name}", {})
                    os.utime(staged, ns=(original.st_atime_ns, original.st_mtime_ns))
                    publish_media(staged, final)
                    try:
                        if review:
                            store.update_clip_metadata(
                                camera_id, final.name, favorite=review.get("favorite"), rejected=review.get("rejected"),
                            )
                    except OSError:
                        final.unlink(missing_ok=True)
                        raise
                outcome.update(status="complete", output_file=final.name, camera_id=camera_id)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            outcome["message"] = str(exc)
        finally:
            try:
                staged.unlink(missing_ok=True)
            finally:
                with self._lock:
                    self._state = {**self._state, **outcome, "elapsed_seconds": round(time.monotonic() - started, 2)}
