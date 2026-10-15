"""test_c_core.py - builds and runs axis-drive's C tests, and links the whole engine. Needs a working C compiler; skipped without one."""
import glob
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))))
import c_compile_check  # noqa: E402

CC = c_compile_check.find_compiler()


@unittest.skipUnless(CC, "no working C compiler on this machine")
class DriveC(unittest.TestCase):
    def test_the_drive_passes_its_tests(self):
        work = tempfile.mkdtemp(prefix="drive_c_")
        exe = os.path.join(work, "t.exe")
        srcs = [os.path.join("src", f) for f in ("core.c", "inject.c", "manifest.c", "port.c", "tip.c")]
        b = subprocess.run(CC + ["-Wall", "-Wextra", "-I", "src", os.path.join("tests", "test_drive.c")] + srcs + ["-o", exe], cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(b.returncode, 0, b.stderr[-800:])
        r = subprocess.run([exe, work], capture_output=True, text=True, timeout=60, cwd=work)
        self.assertEqual(r.returncode, 0, r.stdout[-800:])

    def test_the_whole_engine_links(self):
        exe = os.path.join(tempfile.mkdtemp(prefix="drive_c_"), "d.exe")
        srcs = sorted(glob.glob(os.path.join(ROOT, "src", "*.c")))
        b = subprocess.run(CC + ["-Wall", "-I", "src"] + srcs + ["-o", exe], cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(b.returncode, 0, b.stderr[-800:])


if __name__ == "__main__":
    unittest.main(verbosity=1)
