"""test_c_core.py - builds and runs axis-vision's C tests, and links the whole engine. Needs a working C compiler; skipped without one."""
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
class VisionC(unittest.TestCase):
    def test_the_logic_passes_its_tests(self):
        exe = os.path.join(tempfile.mkdtemp(prefix="vision_c_"), "t.exe")
        b = subprocess.run(CC + ["-Wall", "-I", "src", os.path.join("tests", "test_vision.c"), os.path.join("src", "vision_logic.c"), "-o", exe], cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(b.returncode, 0, b.stderr[-800:])
        r = subprocess.run([exe], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout[-800:])

    def test_the_engine_core_and_research_pass_their_tests(self):
        work = tempfile.mkdtemp(prefix="vision_c_")
        exe = os.path.join(work, "e.exe")
        srcs = [os.path.join("src", f) for f in ("engine_core.c", "research_engine.c", "universal_port.c")]
        b = subprocess.run(CC + ["-Wall", "-Wextra", "-I", "src", os.path.join("tests", "test_engine.c")] + srcs + ["-lm", "-o", exe], cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(b.returncode, 0, b.stderr[-800:])
        r = subprocess.run([exe, work], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout[-800:])

    def test_the_whole_engine_links(self):
        exe = os.path.join(tempfile.mkdtemp(prefix="vision_c_"), "v.exe")
        srcs = sorted(glob.glob(os.path.join(ROOT, "src", "*.c")))
        b = subprocess.run(CC + ["-Wall", "-I", "src"] + srcs + ["-o", exe], cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(b.returncode, 0, b.stderr[-800:])


if __name__ == "__main__":
    unittest.main(verbosity=1)
