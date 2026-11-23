from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import shutil
import subprocess
import unittest

from pydantic import ValidationError

from app.media import validate_mp4
from app.models import PrinterStatusSnapshot
from app.timeline import EventInput, Timeline, TimelineMonitor, extract_segment, video_offset


class TimelineTest(unittest.TestCase):
    def test_dual_timestamps_persist_and_are_distinct(self):
        with TemporaryDirectory(dir=".") as temp:
            event = EventInput(kind="print.start", message="Fixture", source_at="2026-11-23T10:00:00-05:00",
                               klipper_eventtime=210.25)
            row = Timeline(temp).append("printer", event, "submitted")
            self.assertEqual(Timeline(temp).events("printer"), [row])
            self.assertEqual(row["klipper_eventtime"], 210.25)
            self.assertEqual(datetime.fromisoformat(row["received_at"]).utcoffset(), timedelta(0))
            self.assertNotEqual(row["source_at"], row["received_at"])
            self.assertEqual(Timeline(temp).events("other"), [])
            with self.assertRaises(ValueError):
                Timeline(temp).events("../printer")
            with self.assertRaises(ValidationError):
                EventInput(kind="test", message="", source_at="2026-11-23T10:00:00")

    def test_clock_mapping_with_correction_and_boundaries(self):
        anchor = datetime(2026, 11, 23, 15, tzinfo=timezone.utc)
        event = datetime.fromisoformat("2026-11-23T10:00:05-05:00")
        self.assertEqual(video_offset(event, anchor, -1.5, 10), 3.5)
        self.assertIsNone(video_offset(event, anchor, 5, 10))
        self.assertIsNone(video_offset(event, anchor, -6, 10))

    def test_poll_retains_raw_klipper_clock_without_inventing_wall_time(self):
        with TemporaryDirectory(dir=".") as temp:
            timeline = Timeline(temp)
            snapshot = PrinterStatusSnapshot(connection_state="online", monitor_state="printing",
                                             printer_status_text="Printing", current_layer=1,
                                             klipper_eventtime=44.125)
            camera = SimpleNamespace(enabled=True, printer_id="printer", moonraker_url="http://test")
            monitor = TimelineMonitor(timeline, SimpleNamespace(fetch_status=lambda _: snapshot),
                                      lambda: [camera, camera])
            monitor.poll()
            monitor.poll()
            snapshot.current_layer = 2
            monitor.poll()
            rows = timeline.events("printer")
            self.assertEqual([r["kind"] for r in rows], ["printer.status", "print.layer", "print.layer"])
            self.assertTrue(all(r["source_at"] is None and r["klipper_eventtime"] == 44.125 for r in rows))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Requires FFmpeg")
    def test_segment_extraction_preserves_original(self):
        with TemporaryDirectory(dir=".") as temp:
            source, output = (Path(temp).resolve() / name for name in ("source.mp4", "segment.mp4"))
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=20",
                "-t", "4", "-c:v", "libx264", str(source),
            ], check=True, timeout=20)
            original = source.read_bytes()
            with self.assertRaises(ValueError):
                extract_segment(source, output, 1, 5, 0)
            self.assertFalse(output.exists())
            extract_segment(source, output, 1.25, 2.75, 0)
            self.assertAlmostEqual(float(validate_mp4(output)["format"]["duration"]), 1.5, delta=0.051)
            self.assertEqual(source.read_bytes(), original)
