"""test_operational.py - is axis-curator operational? Run: python test_operational.py
Everything loads, and the tools really do their jobs on real files (hashes, sanitising, path safety, tagging)."""
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import bootstrap  # noqa: E402,F401


class Operational(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="curator_")
        cls.file = os.path.join(cls.dir, "a.txt")
        with open(cls.file, "w") as f:
            f.write("hello")

    def test_everything_loads(self):
        import health_report
        self.assertEqual(health_report.problems(), [])

    def test_main_boots_to_system_ready(self):
        import main
        self.assertEqual(main.triad_starter().boot()["status"], "system_ready")

    def test_checksum_detects_a_wrong_hash(self):
        from checksum_verification_tool import ChecksumVerificationTool
        t = ChecksumVerificationTool()
        self.assertEqual(t.execute(self.file, hashlib.sha256(b"hello").hexdigest())["status"], "intact")
        self.assertEqual(t.execute(self.file, "0" * 64)["status"], "mismatch")

    def test_verify_integrity_is_honest_about_unknown_files(self):
        from verify_integrity_tool import VerifyIntegrityTool
        t = VerifyIntegrityTool()
        self.assertEqual(t.check(self.file)["status"], "not_in_manifest")
        self.assertEqual(t.check(os.path.join(self.dir, "missing.txt"))["status"], "error")
        t.engine.config.manifest[self.file] = hashlib.sha256(b"hello").hexdigest()
        self.assertEqual(t.check(self.file)["status"], "verified")
        t.engine.config.manifest[self.file] = "0" * 64
        self.assertEqual(t.check(self.file)["status"], "corrupted")

    def test_sanitizer_strips_markup_noise_and_limits_size(self):
        from denoising_sanitization_tool import DenoisingSanitizationTool
        t = DenoisingSanitizationTool()
        r = t.process("<b>Hi</b> noise_artifact   there\x01")
        self.assertEqual(r["data"], "Hi there")
        self.assertTrue(t.process("x" * 9000)["truncated"])
        self.assertEqual(len(t.process("x" * 9000)["data"]), 8192)

    def test_path_traversal_is_denied(self):
        from curate_input_path_tool import CurateInputPathTool
        t = CurateInputPathTool()
        self.assertEqual(t.get_safe_path("abc")["status"], "resolved")
        self.assertEqual(t.get_safe_path("../../etc")["status"], "denied")

    def test_metadata_tagging(self):
        from automated_metadata_tagging_tool import AutomatedMetadataTaggingTool
        r = AutomatedMetadataTaggingTool().tag_file(self.file)
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["metadata"]["extension"], ".txt")

    def test_master_test_script_runs(self):
        r = subprocess.run([sys.executable, "run_master_test.py"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-300:])


if __name__ == "__main__":
    unittest.main(verbosity=1)
