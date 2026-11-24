import base64
import os
import tempfile
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.access import AccessBoundary, credentials_match
from app.clips import ClipStore
from app.config import resolve_camera
from app.media import redact_diagnostic
from app.models import CameraConfigInput, PrinterStatusSnapshot, RetentionConfig, TimelapseAutoSettings, TimelapseSessionState
from app.retention import RetentionManager
from app.timelapse_auto import TimelapseAutomation
from app.timelapse import ManagedTimelapse, TimelapseManager


class SafetyTests(unittest.TestCase):
    def test_layer_worker_interval_fallback_pause_and_completion(self):
        rows = iter([
            ("printing", None), ("paused", None), ("printing", 2),
            ("printing", 2), ("printing", 3), ("printing", 2), ("complete", 3),
        ])
        captured = []
        clock = SimpleNamespace(now=0.0, stopped=False)

        def fetch(_):
            state, layer = next(rows)
            return PrinterStatusSnapshot(monitor_state=state, current_layer=layer, printer_status_text=state)

        def wait(timeout):
            clock.now += timeout

        with tempfile.TemporaryDirectory(dir=".") as folder:
            root = Path(folder)
            frames = root / "frames"
            frames.mkdir()
            manager = TimelapseManager(folder, SimpleNamespace(fetch_status=fetch), minimum_free_bytes=0)
            session = ManagedTimelapse(
                "printer", "Printer", "view", "View", "not-used", "http://fixture.invalid", 2,
                "fixture", root, frames, root / "fixture.mp4",
                state=TimelapseSessionState(printer_id="printer", session_id="fixture", capture_mode="layer"),
                stop_event=SimpleNamespace(is_set=lambda: clock.stopped, wait=wait,
                                           set=lambda: setattr(clock, "stopped", True)),
            )

            def capture(job):
                captured.append((clock.now, job.current_layer))
                return True

            with patch("app.timelapse.time", SimpleNamespace(monotonic=lambda: clock.now)), \
                    patch.object(manager, "_capture_frame", side_effect=capture), \
                    patch.object(manager, "_render_after_stop") as render:
                manager._run_session(session)
            self.assertEqual(captured, [(0.0, None), (2.0, 2), (4.0, 3)])
            render.assert_called_once_with(session, "moonraker_complete")

    def test_layer_capture_debounces_pause_and_old_layers(self):
        session = SimpleNamespace(printer_printing=True, layer_captured=4)
        due = TimelapseManager._layer_capture_due
        self.assertTrue(due(session, True, 5))
        self.assertFalse(due(session, True, 4))
        self.assertFalse(due(session, True, 3))
        self.assertTrue(due(session, True, None))
        session.printer_printing = False
        self.assertFalse(due(session, True, 5))
        self.assertTrue(due(session, False, None))

    def test_access_credentials_and_lan_default(self):
        header = "Basic " + base64.b64encode(b"admin:test-password").decode()
        self.assertTrue(credentials_match(header, "test-password"))
        self.assertFalse(credentials_match(header, "wrong"))
        self.assertFalse(credentials_match("Basic ###", "test-password"))
        with patch.dict(os.environ, {"APP_BIND_ADDRESS": "0.0.0.0", "APP_ACCESS_PASSWORD": ""}):
            with self.assertRaises(RuntimeError):
                AccessBoundary(None)

    def test_input_validation_and_diagnostics(self):
        with self.assertRaises(ValueError):
            resolve_camera(CameraConfigInput(
                id="cam", name="Printer", mode="manual_urls", record_url="file:///private/video.mp4",
            ))
        self.assertNotIn("secret", redact_diagnostic("Input rtsp://admin:secret@printer.local/video failed"))

    def test_clip_policy_and_cleanup_preview(self):
        with tempfile.TemporaryDirectory(dir=".") as folder:
            root = Path(folder)
            camera = root / "cam"
            camera.mkdir()
            (camera / "note.txt").write_text("not a clip")
            (camera / "temp.mp4.part").write_bytes(b"staging")
            (camera / "favorite.mp4").write_bytes(b"favorite")
            (camera / "eligible.mp4").write_bytes(b"eligible")
            store = ClipStore(str(root))
            self.assertEqual({c.filename for c in store.list_clips([], set())}, {"favorite.mp4", "eligible.mp4"})
            store.update_clip_metadata("cam", "favorite.mp4", favorite=True)
            manager = RetentionManager(str(root), RetentionConfig(
                enabled=True, cleanup_mode="alert_only", max_total_gb=0.000000001,
            ))
            self.assertEqual(manager.preview(set())["eligible_files"], 1)
            self.assertTrue((camera / "eligible.mp4").exists())
            self.assertIsNone(manager.enforce_retention(set(), "automatic"))
            summary = manager.enforce_retention(set(), "manual", manual=True)
            self.assertEqual(summary.deleted_files, 1)
            self.assertTrue((camera / "favorite.mp4").exists())
            self.assertTrue((camera / "temp.mp4.part").exists())

    def test_auto_start_survives_restart_and_pause(self):
        with tempfile.TemporaryDirectory(dir=".") as folder:
            counts = Counter()
            status = SimpleNamespace(monitor_state="printing", job="job-one")
            camera = SimpleNamespace(id="cam", printer_id="printer", enabled=True,
                                     printer_name="Printer", moonraker_url="http://printer")
            def start(*args, print_job_id, **kwargs):
                counts[print_job_id] += 1
            manager = SimpleNamespace(is_printer_busy=lambda _: False, start_session=start)
            moonraker = SimpleNamespace(fetch_status=lambda _: status, active_job_id=lambda _: status.job)
            make = lambda: TimelapseAutomation(folder, manager, moonraker, lambda: [camera])
            auto = make()
            auto.configure("printer", TimelapseAutoSettings(enabled=True, camera_id="cam"))
            auto.poll()
            status.monitor_state = "paused"
            auto.poll()
            status.monitor_state = "offline"
            auto.poll()
            status.monitor_state = "printing"
            auto.poll()
            make().poll()
            status.job = "job-two"
            make().poll()
            self.assertEqual(counts, {"job-one": 1, "job-two": 1})

    def test_concurrent_review_updates_then_rename(self):
        with tempfile.TemporaryDirectory(dir=".") as folder:
            root = Path(folder)
            (root / "cam").mkdir()
            for index in range(12):
                (root / "cam" / f"{index}.mp4").write_bytes(b"fixture")
            store = ClipStore(str(root))
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda index: store.update_clip_metadata("cam", f"{index}.mp4", favorite=True), range(12)))
            store.rename_clip("cam", "0.mp4", "renamed.mp4", [])
            items = store.list_clips([], set())
            self.assertEqual(len(items), 12)
            self.assertTrue(all(item.favorite for item in items))
            self.assertIn("renamed.mp4", {item.filename for item in items})
