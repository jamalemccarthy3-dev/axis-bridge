"""test_operational.py - is axis-video_creator operational? Run: python test_operational.py
Every silo imports, the shared tools really work, and the CGI tools instantiate. Stubs are allowed to exist but must say so (they raise when called)."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import health_report  # noqa: E402
from config.master_config import SILO_REGISTRY  # noqa: E402


class Operational(unittest.TestCase):
    def test_every_silo_folder_exists_and_imports(self):
        broken = {}
        for name, rel in SILO_REGISTRY.items():
            for f, (st, why) in health_report.check(name, rel).items():
                if st in ("MISSING", "IMPORT_ERROR", "PROBE_FAILED"):
                    broken["%s/%s" % (name, f)] = why
        self.assertEqual(broken, {})

    def test_root_tools_work(self):
        from root_tools.lib import crypto, loader, logger
        self.assertEqual(crypto.generate_hash({"a": 1, "b": 2}), crypto.generate_hash({"b": 2, "a": 1}))
        self.assertNotEqual(crypto.generate_hash("x"), crypto.generate_hash("y"))
        self.assertEqual(len(crypto.generate_hash("x")), 64)
        self.assertEqual(loader.load_config("no/such/file.json"), {})
        self.assertIn("TestAgent", logger.log_action("TestAgent", "t", "ok"))

    def test_a_silo_request_runs_end_to_end(self):
        sys.path.insert(0, os.path.join(ROOT, "silos", "vision_narrative_architect"))
        import request_tool
        res = request_tool.execute_narrative_task("parse", {"scene": 1})
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["narrative_hash"]), 64)
        sys.path.pop(0)

    def test_local_bus_delivers(self):
        from bus.protocol import broadcast_message
        r = broadcast_message({"hello": "world"})
        self.assertTrue(r["delivered"])

    def test_cgi_tools_instantiate(self):
        r = subprocess.run([sys.executable, "test_cgi_silo.py"], cwd=os.path.join(ROOT, "silos", "cgi"), capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-300:])

    def test_the_narrative_builder_is_real_and_refuses_nothing_to_build_from(self):
        sys.path.insert(0, os.path.join(ROOT, "silos", "vision_narrative_architect"))
        from lib import schema_builder
        schema = schema_builder.build_narrative_schema("First thing. Second thing.")
        self.assertEqual((schema["status"], len(schema["beats"])), ("pristine", 2))
        with self.assertRaises(ValueError):
            schema_builder.build_narrative_schema({})
        sys.path.pop(0)
        sys.modules.pop("lib", None)


if __name__ == "__main__":
    unittest.main(verbosity=1)
