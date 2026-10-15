"""test_operational.py - is axis-validator operational? Run: python test_operational.py"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


class Operational(unittest.TestCase):
    def test_every_module_imports(self):
        import health_report
        bad = {k: v[1] for k, v in health_report.check().items() if v[0] in ("IMPORT_ERROR", "PROBE_FAILED")}
        self.assertEqual(bad, {})

    def test_registry_matches_the_disk(self):
        r = subprocess.run([sys.executable, "master_config.py"], cwd=ROOT, capture_output=True, text=True, timeout=60, env=dict(os.environ, NEXXUS_MESH_URL="http://127.0.0.1:9"))
        self.assertEqual(r.returncode, 0, r.stdout[-400:])

    def test_every_src_module_has_its_config_and_tool(self):
        src = os.path.join(ROOT, "src")
        missing = []
        for f in sorted(os.listdir(src)):
            if f.endswith(".py") and f != "__init__.py":
                name = f[:-3]
                for sub, suffix in (("config", "_config.py"), ("lib", "_tool.py")):
                    if not os.path.isfile(os.path.join(src, sub, name + suffix)):
                        missing.append("%s/%s%s" % (sub, name, suffix))
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
