from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import shutil
import subprocess
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi import HTTPException

from pydantic import ValidationError

from app.media import validate_mp4
from app.api.timeline import CalibrationUpdate, ClipRange, _printer, extract_clip, read_timeline, update_calibration
from app.camera_store import CameraConfigStore
from app.clips import ClipStore
from app.config import resolve_camera
from app.models import CameraConfigInput, CameraUpsertRequest, PrinterConfigInput, PrinterStatusSnapshot
from app.printers import build_printer_cards
from app.services.moonraker_service import MoonrakerService
from app.operations import camera_lock
from app.timeline import EventInput, Timeline, TimelineMonitor, export_captions, extract_segment, video_offset


class TimelineTest(unittest.TestCase):
    def test_clip_catalog_limit_keeps_quieter_camera_available(self):
        cameras = [SimpleNamespace(id=cid, name=cid, printer_id="printer") for cid in ("busy", "quiet")]
        now = datetime.now(timezone.utc)

        def clips(_cameras, _active, cid):
            count = 251 if cid == "busy" else 1
            return [SimpleNamespace(camera_id=cid, filename=f"{i}.mp4", active=False,
                                    created_at=now - timedelta(seconds=i if cid == "busy" else 1000))
                    for i in range(count)]

        state = SimpleNamespace(cameras=cameras, runtime_state=SimpleNamespace(active_output_paths=set),
                                timeline=SimpleNamespace(events=lambda _: []),
                                clip_store=SimpleNamespace(list_clips=clips, timeline_timings=dict))
        result = read_timeline("printer", SimpleNamespace(app=SimpleNamespace(state=state)))
        self.assertEqual(len(result["clips"]), 251)
        self.assertEqual(result["clips"][-1]["camera_id"], "quiet")

    def test_klipper_log_clock_restarts_and_parallel_duplicate_imports(self):
        log = (
            "Stats 33.0: no startup yet\n"
            "Start printer at first (1700000000.0 100.0)\n"
            "Stats 101.25: discarded raw token=secret\n"
            "Transition to shutdown state: don't persist this\n"
            "Restarting printer\nStats 103.0: unknown session\n"
            "Start printer at second (1700001000.0 500.0)\n"
            "Stats 503.0: discarded\n"
        )
        with TemporaryDirectory(dir=".") as temp, ThreadPoolExecutor(max_workers=6) as pool:
            timeline = Timeline(temp)
            jobs = [pool.submit(timeline.import_klipper, "cam", log) for _ in range(6)]
            jobs += [pool.submit(timeline.append, "cam", EventInput(kind="note", message=str(n)), "test")
                     for n in range(20)]
            self.assertEqual(sum(job.result()["imported"] for job in jobs[:6]), 5)
            for job in jobs[6:]:
                job.result()
            rows = timeline.events("cam")
            self.assertEqual(len(rows), 25)
            self.assertEqual(len({row["id"] for row in rows}), len(rows))
            imported = [row for row in rows if row["origin"] == "klipper-log"]
            self.assertEqual([datetime.fromisoformat(row["source_at"]).timestamp() for row in imported],
                             [1700000000, 1700000001.25, 1700000001.25, 1700001000, 1700001003])
            self.assertTrue(all(row["source_at"] != row["received_at"] for row in imported))
            self.assertNotIn("secret", str(rows))
            self.assertNotIn("don't persist", str(rows))

    def test_export_pins_source_and_releases_camera_lock_before_encoding(self):
        with TemporaryDirectory(dir=".") as temp, ThreadPoolExecutor(max_workers=1) as pool:
            root = Path(temp).resolve()
            source = root / "camera" / "clip.mp4"
            source.parent.mkdir()
            source.write_bytes(b"original")
            state = SimpleNamespace(
                cameras=[], clip_store=ClipStore(temp), runtime_state=SimpleNamespace(active_output_paths=set),
                optimizer=SimpleNamespace(active_paths=set), timelapse_manager=SimpleNamespace(active_paths=set),
                settings={"recordings_dir": temp},
                app_config=SimpleNamespace(retention=SimpleNamespace(capture_reserve_mib=0)),
            )
            request = SimpleNamespace(app=SimpleNamespace(state=state))
            entered, resume = Event(), Event()

            def encode(snapshot, output, *_args, **_kwargs):
                entered.set()
                self.assertTrue(resume.wait(4))
                output.write_bytes(snapshot.read_bytes())

            with patch("app.api.timeline.extract_segment", side_effect=encode):
                future = pool.submit(extract_clip, "camera", source.name, ClipRange(start=0, end=1), request)
                try:
                    if not entered.wait(4) and future.done():
                        future.result()
                    self.assertTrue(entered.is_set())
                    with self.assertRaises(HTTPException) as busy:
                        extract_clip("camera", source.name, ClipRange(start=0, end=1), request)
                    self.assertEqual(busy.exception.status_code, 409)
                    self.assertTrue(camera_lock.acquire(timeout=1))
                    try:
                        source.rename(source.with_name("renamed.mp4"))
                        source.write_bytes(b"replacement")
                    finally:
                        camera_lock.release()
                finally:
                    resume.set()
                response = future.result(5)
            self.assertEqual(Path(response.path).read_bytes(), b"original")
            response.background.func()
            self.assertFalse(Path(response.path).exists())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Requires FFmpeg")
    def test_timestamped_export_burns_text_without_changing_source(self):
        with TemporaryDirectory(dir=".") as temp:
            folder = Path(temp).resolve()
            source, output = folder / "source.mp4", folder / "segment.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:size=360x240:rate=15",
                            "-t", "3", "-c:v", "libx264", str(source)], check=True, timeout=15)
            zero = datetime.fromisoformat("2026-11-23T10:00:00+00:00")
            track = folder / "timestamps.srt"
            export_captions(track, [{"source_at": "2026-11-23T10:00:01+00:00",
                                     "received_at": "2026-11-23T10:00:02+00:00"}], zero, 1, 2, "source")
            text = track.read_text(encoding="utf-8")
            self.assertIn("Source: 2026-11-23T10:00:01", text)
            self.assertIn("Received: 2026-11-23T10:00:02", text)
            before = source.read_bytes()
            extract_segment(source, output, 1, 2, 0, burn_timestamps=True)
            pixels = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(output),
                                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                                             timeout=15)
            self.assertGreater(max(pixels), 100)
            self.assertAlmostEqual(float(validate_mp4(output)["format"]["duration"]), 1.0, delta=0.07)
            self.assertEqual(source.read_bytes(), before)

    def test_moonraker_retains_last_good_readings_but_reports_offline(self):
        service = MoonrakerService()
        self.addCleanup(service.shutdown)
        success = datetime.now(timezone.utc)
        good = PrinterStatusSnapshot(
            connection_state="online", monitor_state="printing", metadata_available=True,
            progress_percent=42, extruder_current_temp=200, klipper_eventtime=53,
            last_metadata_attempt_at=success, last_metadata_success_at=success,
        )
        outage = PrinterStatusSnapshot(
            connection_state="offline", monitor_state="offline",
            last_metadata_attempt_at=success + timedelta(seconds=2),
        )
        with patch.object(service, "_read_status", side_effect=[good, outage]), \
                patch("app.services.moonraker_service.time.monotonic", side_effect=[1, 3, 3]):
            self.assertTrue(service.fetch_status("http://printer").metadata_available)
            state = service.fetch_status("http://printer")
        self.assertEqual(state.monitor_state, "offline")
        self.assertFalse(state.metadata_available)
        self.assertEqual(state.last_metadata_success_at, success)
        self.assertEqual(state.extruder_current_temp, 200)
        self.assertEqual(state.progress_percent, 42)
        self.assertIsNone(state.klipper_eventtime)

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
