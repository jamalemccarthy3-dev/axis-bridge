"""test_c_all.py - every C engine file really compiles (c_compile_check.py), and the engines' C test programs build and pass.
Needs a working C compiler (gcc/cc/clang on PATH, C_COMPILER, or `pip install ziglang`); it is skipped, not failed, when there is none. Run: python test_c_all.py"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import c_compile_check  # noqa: E402

CC = c_compile_check.find_compiler()
SILO = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault")


@unittest.skipUnless(CC, "no working C compiler on this machine")
class AllC(unittest.TestCase):
    def test_every_c_file_compiles(self):
        self.assertEqual(c_compile_check.main([]), 0)

    def test_the_engines_c_test_programs_pass(self):
        for engine in ("axis-omni", "axis-core", "axis-vision", "axis-drive", "axis-vantage_point"):
            r = subprocess.run([sys.executable, "test_c_core.py"], cwd=os.path.join(SILO, engine), capture_output=True, text=True, timeout=400)
            self.assertEqual(r.returncode, 0, engine + ": " + r.stderr[-500:])


if __name__ == "__main__":
    unittest.main(verbosity=1)
