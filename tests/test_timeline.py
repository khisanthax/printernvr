from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import shutil
import subprocess
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.media import validate_mp4
from app.api.timeline import CalibrationUpdate, _printer, update_calibration
from app.camera_store import CameraConfigStore
from app.clips import ClipStore
from app.config import resolve_camera
from app.models import CameraConfigInput, CameraUpsertRequest, PrinterConfigInput, PrinterStatusSnapshot
from app.printers import build_printer_cards
from app.timeline import EventInput, Timeline, TimelineMonitor, extract_segment, video_offset


class TimelineTest(unittest.TestCase):
    def test_event_log_compacts_to_recent_rows(self):
        with TemporaryDirectory(dir=".") as temp, patch("app.timeline.MAX_LOG_BYTES", 2048):
            timeline = Timeline(temp)
            for n in range(20):
                timeline.append("demo", EventInput(kind="note", message=f"{n}: " + chr(0x1F600) * 100), "test")
            rows = timeline.events("demo")
            self.assertGreater(len(rows), 1)
            self.assertLess(len(rows), 20)
            self.assertTrue(rows[-1]["message"].startswith("19: "))
            self.assertLess((Path(temp) / ".timeline" / "demo.jsonl").stat().st_size, 2680)

    def test_archive_folder_collision_resolves_indexed_media(self):
        with TemporaryDirectory(dir=".") as temp:
            root = Path(temp).resolve()
            camera = resolve_camera(CameraConfigInput(
                id="cam", name="Cam", mode="manual_urls", record_url="rtsp://camera/stream",
                output_subdir="new-folder",
            ))
            for folder in ("cam", "new-folder", ".timeline-export-temp"):
                path = root / folder / "clip.mp4"
                path.parent.mkdir()
                path.write_text(folder, encoding="utf-8")
            store = ClipStore(temp)
            clips = store.list_clips([camera], set())
            self.assertEqual({clip.camera_id for clip in clips}, {"archive:cam", "cam"})
            for clip in clips:
                self.assertEqual(store.resolve_clip_path(clip.camera_id, clip.filename, [camera]),
                                 root / clip.relative_path)
                self.assertEqual(clip.created_at.utcoffset(), timedelta(0))
            self.assertEqual(store.list_clips([camera], set(), "archive:../cam"), [])
            with self.assertRaises(ValueError):
                store.resolve_clip_path(".timeline-export-temp", "clip.mp4", [camera])

    def test_compatibility_camera_crud_keeps_empty_printer_and_settings(self):
        with TemporaryDirectory(dir=".") as temp:
            store = CameraConfigStore(str(Path(temp) / "cameras.json"))
            store.save_printers([PrinterConfigInput(
                id="demo", name="Demo", display_order=14, moonraker_url="http://printer.example",
            )])
            payload = CameraUpsertRequest(id="camera", name="Camera", printer_id="demo",
                                          mode="manual_urls", record_url="rtsp://camera/stream",
                                          output_subdir="archive-folder")
            store.create_camera(payload)
            store.update_camera("camera", payload.model_copy(update={
                "id": None, "printer_id": None, "output_subdir": None, "name": "Changed",
            }))
            printers, _, cameras = store.list_printers()
            self.assertEqual(cameras[0].output_subdir, "archive-folder")
            self.assertEqual(printers[0].default_camera_id, "camera")
            store.delete_camera("camera")
            printers, _, cameras = store.list_printers()
            self.assertEqual(cameras, [])
            self.assertEqual(printers[0].id, "demo")
            self.assertIsNone(printers[0].default_camera_id)
            self.assertEqual(printers[0].display_order, 14)
            self.assertEqual(printers[0].moonraker_url, "http://printer.example")

    def test_calibration_round_trip_without_replacing_recording_anchor(self):
        with TemporaryDirectory(dir=".") as temp:
            root = Path(temp)
            source = root / "camera" / "clip.mp4"
            source.parent.mkdir()
            source.touch()
            store = ClipStore(temp)
            state = SimpleNamespace(
                cameras=[], clip_store=store, runtime_state=SimpleNamespace(active_output_paths=set),
                optimizer=SimpleNamespace(active_paths=set),
            )
            request = SimpleNamespace(app=SimpleNamespace(state=state))
            estimate = {"frame_zero_at": "2026-11-23T15:00:00Z"}
            store.save_recording_anchor("camera", source.name, estimate)
            correction = CalibrationUpdate(calibration={
                "frame_zero_at": "2026-11-23T10:00:05-05:00", "correction_seconds": -1.25,
            })
            result = update_calibration("camera", source.name, correction, request)
            self.assertEqual(ClipStore(temp).timeline_calibration("camera", source.name), result["calibration"])
            update_calibration("camera", source.name, CalibrationUpdate(calibration=None), request)
            self.assertIsNone(ClipStore(temp).timeline_calibration("camera", source.name))
            self.assertEqual(ClipStore(temp).recording_anchor("camera", source.name), estimate)

    def test_printer_first_monitoring_without_view(self):
        with TemporaryDirectory(dir=".") as temp:
            store = CameraConfigStore(str(Path(temp) / "cameras.json"))
            store.save_printers([
                PrinterConfigInput(id="demo", name="Demo", moonraker_url="http://printer.example"),
                PrinterConfigInput(id="disabled", name="Disabled", enabled=False,
                                   moonraker_url="http://disabled.example"),
            ])
            printers, _, cameras = store.list_printers()
            observed = []

            def fetch(url):
                observed.append(url)
                return PrinterStatusSnapshot(printer_status_text="Idle", monitor_state="idle")

            service = SimpleNamespace(fetch_status=fetch)
            cards = {card.printer_id: card for card in build_printer_cards(cameras, service, printers=printers)}
            self.assertEqual(cards["demo"].printer_status_text, "Idle")
            self.assertFalse(cards["demo"].camera_enabled)
            self.assertEqual(cards["demo"].available_views, [])
            self.assertNotIn("http://disabled.example", observed)
            self.assertEqual(_printer(SimpleNamespace(cameras=cameras, printers=printers), "demo"), [])
            timeline = Timeline(temp)
            TimelineMonitor(timeline, service, lambda: cameras, lambda: printers).poll()
            self.assertEqual(timeline.events("demo")[0]["message"], "Idle")
            self.assertEqual(timeline.events("disabled"), [])

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
