from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from shutil import disk_usage

from app.media import validate_mp4


@lru_cache(maxsize=2048)
def _probe(path: Path, mtime_ns: int, size: int) -> dict:
    try:
        return validate_mp4(path)
    except ValueError:
        return {}


def build_inventory(root: Path, store, cameras, active_paths: set[str]) -> dict:
    root = root.resolve()
    groups = defaultdict(lambda: {
        "count": 0, "bytes": 0, "duration_seconds": 0.0, "measured_bytes": 0,
        "video_formats": set(), "review": Counter(), "oldest": None, "newest": None,
    })
    for clip in store.list_clips(cameras, active_paths):
        if clip.active:
            continue
        group = groups[clip.camera_id]
        path = store.resolve_clip_path(clip.camera_id, clip.filename, cameras)
        try:
            stat = path.stat()
        except OSError:
            continue
        group["bytes"] += clip.size_bytes
        group["count"] += 1
        group["review"]["favorite" if clip.favorite else "rejected" if clip.rejected else "unreviewed"] += 1
        timestamp = clip.created_at.isoformat()
        group["oldest"] = min(group["oldest"] or timestamp, timestamp)
        group["newest"] = max(group["newest"] or timestamp, timestamp)
        if metadata := _probe(path, stat.st_mtime_ns, stat.st_size):
            stream = metadata["streams"][0]
            group["duration_seconds"] += float(metadata["format"]["duration"])
            group["measured_bytes"] += clip.size_bytes
            group["video_formats"].add((stream["codec_name"], stream["width"], stream["height"], stream.get("avg_frame_rate")))
    totals = Counter()
    for key, group in groups.items():
        bitrate = group["measured_bytes"] * 8 / group["duration_seconds"] if group["duration_seconds"] else None
        group["camera_id"] = key
        group["average_bytes"] = group["bytes"] // group["count"]
        group["average_bits_per_second"] = bitrate
        group["projection_bytes"] = {
            str(hours): round(bitrate * hours * 450) for hours in (1, 8, 24, 168, 720)
        } if bitrate else {}
        group["video_formats"] = [list(row) for row in sorted(group["video_formats"], key=repr)]
        totals.update(group["review"])
        totals["completed_clips"] += group["count"]
        totals["clip_bytes"] += group["bytes"]
    for path in root.rglob("*"):
        if not path.is_file() or path.resolve() != path:
            continue
        parts = path.relative_to(root).parts
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if path.suffix == ".part":
            totals["temporary_bytes"] += size
        elif parts[0] == "timelapses" and path.suffix == ".mp4":
            totals["timelapse_mp4_bytes"] += size
        elif parts[0] == "timelapses" and path.suffix == ".jpg":
            totals["timelapse_frame_bytes"] += size
    return {"free_bytes": disk_usage(root).free, "totals": dict(totals), "cameras": list(groups.values())}
