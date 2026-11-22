import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from app.clips import ClipStore
from app.config import resolve_camera
from app.media import validate_mp4
from app.models import CameraConfigInput
from app.recorder import RecordingManager
from app.state import RuntimeStateManager


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
            id="front", name="Front", mode="manual_urls", record_url=str(self.source),
        ))
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


if __name__ == "__main__":
    unittest.main()
