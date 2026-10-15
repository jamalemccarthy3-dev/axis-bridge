"""test_operational.py - is axis-sweep (a JavaScript engine) operational? Needs Node. Run: python test_operational.py
Syntax-checks every .js file, runs the engine's own test suite (node --test) and starts the engine once."""
import glob
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node.js is not installed")
class Operational(unittest.TestCase):
    def test_every_js_file_parses(self):
        bad = {}
        for f in glob.glob(os.path.join(ROOT, "**", "*.js"), recursive=True) + glob.glob(os.path.join(ROOT, "test", "*.mjs")):
            r = subprocess.run([NODE, "--check", f], capture_output=True, text=True, timeout=60)
            if r.returncode:
                bad[os.path.relpath(f, ROOT)] = r.stderr.strip().splitlines()[0] if r.stderr.strip() else "syntax error"
        self.assertEqual(bad, {})

    def test_the_engine_test_suite_passes(self):
        r = subprocess.run([NODE, "--test", os.path.join("test", "sweep.test.mjs")], cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout[-600:])

    def test_the_engine_starts(self):
        r = subprocess.run([NODE, os.path.join("src", "main.js")], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        self.assertIn("ready for command", r.stdout)

    def test_the_registry_matches_the_disk(self):
        r = subprocess.run([sys.executable, os.path.join("config", "master_config.py")], cwd=ROOT, capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, NEXXUS_MESH_URL="http://127.0.0.1:9"))
        self.assertEqual(r.returncode, 0, r.stdout[-400:])


if __name__ == "__main__":
    unittest.main(verbosity=1)
