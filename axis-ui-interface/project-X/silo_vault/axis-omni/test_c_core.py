"""test_c_core.py - builds and runs Omni's C core tests. Needs a working C compiler (gcc/cc/clang on PATH, C_COMPILER, or `pip install ziglang`); skipped without one."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))))
import c_compile_check  # noqa: E402

CC = c_compile_check.find_compiler()
LIB = ["post", "metronome", "pace_controller", "vibe_profiles", "speech_engine", "synthesizer", "pipe", "system_registry", "generator", "logger"]


@unittest.skipUnless(CC, "no working C compiler on this machine")
class OmniC(unittest.TestCase):
    def test_the_c_core_builds_and_passes(self):
        exe = os.path.join(tempfile.mkdtemp(prefix="omni_c_"), "test_omni_core.exe")
        srcs = [os.path.join("tests", "test_omni_core.c"), os.path.join("src", "input_handler.c")] + [os.path.join("lib", n + ".c") for n in LIB]
        build = subprocess.run(CC + ["-Wall", "-Wno-unused-function", "-I", "lib", "-I", "src"] + srcs + ["-lm", "-o", exe], cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(build.returncode, 0, build.stderr[-800:])
        run = subprocess.run([exe], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout[-800:])
        self.assertIn("passed", run.stdout)

    def test_the_whole_engine_compiles_and_links_with_its_main(self):
        exe = os.path.join(tempfile.mkdtemp(prefix="omni_c_"), "omni.exe")
        srcs = [os.path.join("src", "main.c"), os.path.join("src", "input_handler.c")] + [os.path.join("lib", n + ".c") for n in LIB + ["aggregator"]]
        build = subprocess.run(CC + ["-Wall", "-I", "lib", "-I", "src"] + srcs + ["-lm", "-o", exe], cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(build.returncode, 0, build.stderr[-800:])
        run = subprocess.run([exe], cwd=ROOT, input="start session\nlet's build\n", capture_output=True, text=True, timeout=30)   # ends at the end of the input
        self.assertEqual(run.returncode, 0)
        self.assertIn("Registry Status", run.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
