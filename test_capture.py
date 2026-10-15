import os
import tempfile
import unittest
from unittest import mock

import capture as cap


class CaptureTest(unittest.TestCase):
    def setUp(self):
        t = tempfile.mkdtemp()
        cap.CAPTURE_DIR = os.path.join(t, "c")
        cap.STATE_PATH = os.path.join(t, "s", "p.json")
        cap.AUDIT_PATH = os.path.join(t, "l", "a.jsonl")
        cap._REC.update(proc=None, path=None, started=None, seconds=0)

    def test_off_by_default_and_refusals_are_audited(self):
        self.assertEqual(cap.permissions(), {"screen": False, "camera": False})
        for fn in (cap.screen_snapshot, cap.start_recording, cap.camera_snapshot):
            with self.assertRaises(cap.CaptureError):
                fn()
        self.assertEqual(sum(1 for _ in open(cap.AUDIT_PATH)), 3)

    def test_permissions_are_independent(self):
        cap.set_permission("screen", True)
        self.assertEqual(cap.permissions(), {"screen": True, "camera": False})
        with self.assertRaises(cap.CaptureError):
            cap.camera_snapshot()
        with self.assertRaises(cap.CaptureError):
            cap.set_permission("microphone", True)

    def test_screen_snapshot_saves_png(self):
        cap.set_permission("screen", True)
        try:
            r = cap.screen_snapshot()
        except cap.CaptureError:
            self.skipTest("no display available")
        self.assertTrue(r["path"].endswith(".png") and r["bytes"] > 0)

    def test_recording_is_capped_and_single(self):
        cap.set_permission("screen", True)
        fake = mock.Mock(poll=mock.Mock(return_value=None), stdin=mock.Mock())
        with mock.patch("subprocess.Popen", return_value=fake) as pop, mock.patch.object(cap, "_ffmpeg", return_value="ffmpeg"):
            r = cap.start_recording(9999)
            self.assertEqual(r["seconds"], cap.MAX_RECORD_SECONDS)
            self.assertIn(str(cap.MAX_RECORD_SECONDS), pop.call_args[0][0])
            with self.assertRaises(cap.CaptureError):
                cap.start_recording(5)
            cap.stop_recording()
            fake.stdin.write.assert_called_with(b"q")

    def test_switching_screen_off_stops_recording(self):
        cap.set_permission("screen", True)
        fake = mock.Mock(poll=mock.Mock(return_value=None), stdin=mock.Mock())
        with mock.patch("subprocess.Popen", return_value=fake), mock.patch.object(cap, "_ffmpeg", return_value="ffmpeg"):
            cap.start_recording(5)
            cap.set_permission("screen", False)
        fake.stdin.write.assert_called_with(b"q")

    def test_analyze_needs_model_and_safe_name(self):
        with mock.patch.dict(os.environ, {"NEXXUS_VISION_MODEL": ""}):
            with self.assertRaises(cap.CaptureError):
                cap.analyze("a.png")
        with mock.patch.dict(os.environ, {"NEXXUS_VISION_MODEL": "llava"}):
            with self.assertRaises(cap.CaptureError):
                cap.analyze("../secrets.png")


if __name__ == "__main__":
    unittest.main()
