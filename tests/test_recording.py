import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.clips import ClipStore
from app.config import resolve_camera
from app.media import validate_mp4
from app.models import CameraConfigInput
from app.recorder import RecordingManager
from app.state import RuntimeStateManager
from app.timelapse import TimelapseManager
from app.models import TimelapseSessionState
from app.inventory import build_inventory
from app.optimizer import Optimizer


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Requires FFmpeg and FFprobe")
class RecordingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=".")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=15",
             "-t", "8", "-c:v", "mpeg4", "-g", "5", str(self.source)], check=True, timeout=15,
        )
        self.camera = resolve_camera(CameraConfigInput(
            id="front", name="Front", mode="manual_urls", record_url="rtsp://localhost/front",
        )).model_copy(update={"record_url": str(self.source)})
        self.state = RuntimeStateManager()
        self.state.initialize([self.camera])
        self.manager = RecordingManager(str(self.root / "recordings"), self.state, minimum_free_bytes=0)
        self.addCleanup(self.manager.shutdown)
        original = self.manager._build_ffmpeg_command

        def paced(*args):
            command = original(*args)
            command.insert(command.index("-i"), "-re")
            return command

        self.manager._build_ffmpeg_command = paced

    def wait_for_finish(self):
        deadline = time.monotonic() + 20
        while self.manager.is_recording(self.camera.id) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(self.manager.is_recording(self.camera.id))
        return self.state.get_state(self.camera.id)

    def test_manual_stop_publishes_verified_video(self):
        started = self.manager.start_recording(self.camera)
        final = Path(started.output_path)
        self.assertFalse(final.exists())
        self.assertIn(str(final), self.state.active_output_paths())
        with self.assertRaises(ValueError):
            self.manager.start_recording(self.camera)
        store = ClipStore(str(self.root / "recordings"))
        staged = final.with_suffix(".mp4.part")
        self.assertEqual(store.list_clips([self.camera], set()), [])
        with self.assertRaises(ValueError):
            store.resolve_clip_path(self.camera.id, staged.name, [self.camera])
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and staged.stat().st_size == 0:
            time.sleep(0.05)
        time.sleep(0.8)
        self.manager.stop_recording(self.camera.id)
        self.manager.stop_recording(self.camera.id)
        result = self.wait_for_finish()
        self.assertEqual(result.status, "idle", result.model_dump())
        self.assertEqual(result.last_completed_output, final.name)
        self.assertTrue(validate_mp4(final)["streams"])
        self.assertFalse(staged.exists())

    def test_timed_recording_and_distinct_names(self):
        first = self.manager.start_recording(self.camera, duration=1)
        self.assertEqual(self.wait_for_finish().status, "idle")
        second = self.manager.start_recording(self.camera, duration=1)
        self.assertEqual(self.wait_for_finish().status, "idle")
        self.assertNotEqual(first.output_path, second.output_path)
        for recording in (first, second):
            self.assertTrue(validate_mp4(Path(recording.output_path))["streams"])

    def test_invalid_input_does_not_publish(self):
        self.source.write_bytes(b"not media")
        started = self.manager.start_recording(self.camera)
        result = self.wait_for_finish()
        self.assertEqual(result.status, "error")
        self.assertIsNone(result.last_completed_output)
        self.assertFalse(Path(started.output_path).exists())

    def test_inventory_and_optimize_preserve_original(self):
        root = self.root / "recordings"
        target = root / self.camera.output_subdir
        target.mkdir(parents=True)
        original = target / "original.mp4"
        shutil.copyfile(self.source, original)
        before = original.read_bytes()
        store = ClipStore(str(root))
        store.update_clip_metadata(self.camera.id, original.name, favorite=True)
        inventory = build_inventory(root, store, [self.camera], set())
        self.assertEqual(inventory["totals"]["favorite"], 1)
        self.assertGreater(inventory["cameras"][0]["projection_bytes"]["8"], len(before))
        optimizer = Optimizer()
        optimizer.start(original, 0, 23, store, self.camera.id)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and optimizer.status()["status"] == "running":
            time.sleep(0.1)
        result = optimizer.status()
        self.assertIn(result["status"], {"complete", "skipped"}, result)
        self.assertEqual(original.read_bytes(), before)
        if result["status"] == "complete":
            self.assertGreaterEqual(result["savings_percent"], 20)
            self.assertTrue(validate_mp4(target / result["output_file"])["streams"])

    def test_interrupted_timelapse_can_render_after_restart(self):
        recordings = self.root / "timelapse-recordings"
        directory = recordings / "timelapses" / "demo" / "test-session"
        frames = directory / "frames"
        frames.mkdir(parents=True)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(self.source), "-frames:v", "3",
             "-threads", "1", str(frames / "frame_%06d.jpg")], check=True, timeout=10,
        )
        state = TimelapseSessionState(printer_id="demo", camera_id="front", session_id="test-session",
                                     status="rendering")
        (directory / "session.json").write_text(state.model_dump_json(), encoding="utf-8")
        manager = TimelapseManager(str(recordings), None, minimum_free_bytes=0)
        self.assertEqual(len(manager.recoverable_sessions()), 1)
        self.assertEqual(manager.list_outputs(), [])
        manager.retry_render("demo", "test-session")
        deadline = time.monotonic() + 10
        while manager.is_printer_busy("demo") and time.monotonic() < deadline:
            time.sleep(0.05)
        state = manager.get_state("demo")
        self.assertEqual(state.status, "complete", state)
        self.assertTrue(validate_mp4(directory / "test-session.mp4")["streams"])
        self.assertEqual(manager.list_outputs()[0]["camera_id"], "front")
        self.assertEqual(manager.recoverable_sessions(), [])

    def test_shutdown_interrupts_render_and_keeps_source_frames(self):
        recordings = self.root / "timelapse-recordings"
        directory = recordings / "timelapses" / "demo" / "test-session"
        frames = directory / "frames"
        frames.mkdir(parents=True)
        frame = frames / "frame_000001.jpg"
        frame.write_bytes(b"existing frame")
        state = TimelapseSessionState(printer_id="demo", camera_id="front", session_id="test-session",
                                     status="rendering")
        (directory / "session.json").write_text(state.model_dump_json(), encoding="utf-8")
        manager = TimelapseManager(str(recordings), None, minimum_free_bytes=0)
        self.addCleanup(manager.shutdown)
        command = [sys.executable, "-c",
                   "from pathlib import Path; import sys, time; Path(sys.argv[1]).touch(); time.sleep(60)",
                   str(directory / "test-session.mp4.part")]
        with patch("app.timelapse._render_command", return_value=command):
            manager.retry_render("demo", "test-session")
            deadline = time.monotonic() + 5
            while not Path(command[-1]).exists() and time.monotonic() < deadline:
                time.sleep(0.025)
            self.assertTrue(Path(command[-1]).exists())
            manager.shutdown()
        self.assertFalse(manager.is_printer_busy("demo"))
        self.assertEqual(manager.get_state("demo").stop_reason, "app_shutdown")
        self.assertFalse(Path(command[-1]).exists())
        self.assertEqual(frame.read_bytes(), b"existing frame")
        self.assertEqual(len(manager.recoverable_sessions()), 1)
        self.assertEqual(manager.list_outputs(), [])


if __name__ == "__main__":
    unittest.main()
