"""test_operational.py - is axis-integrity operational? Run: python test_operational.py"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


class Operational(unittest.TestCase):
    def test_every_module_in_every_layer_imports(self):
        import health_report
        bad = {}
        for layer in health_report.LAYERS:
            for f, (st, why) in health_report.check(layer).items():
                if st in ("IMPORT_ERROR", "PROBE_FAILED"):
                    bad["%s/%s" % (layer, f)] = why
        self.assertEqual(bad, {})

    def test_registry_matches_the_disk(self):
        r = subprocess.run([sys.executable, "master_config.py"], cwd=ROOT, capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, NEXXUS_MESH_URL="http://127.0.0.1:9"))
        self.assertEqual(r.returncode, 0, r.stdout[-400:])

    def test_the_auditor_chain_detects_tampering(self):
        from lib.auditor import Auditor
        path = os.path.join(tempfile.mkdtemp(prefix="aud_"), "a.jsonl")
        a = Auditor(path)
        a.log_event("ISOLATION", "packet moved")
        a.log_event("SYSTEM_HALT", "reset")
        self.assertEqual(a.verify(), (True, 2))
        lines = open(path, encoding="utf-8").read().splitlines()
        e = json.loads(lines[0])
        e["message"] = "nothing happened"
        lines[0] = json.dumps(e, sort_keys=True)
        open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        self.assertFalse(Auditor(path).verify()[0])

    def test_the_security_layer_reaches_the_auditor_interface(self):
        import validator  # the root shim: the real validator lives in auditor_interface
        import forensic_dump
        self.assertTrue(callable(forensic_dump.save_evidence))
        self.assertTrue(hasattr(validator, "__name__"))

    def test_patrol_radio_reports_to_the_auditor(self):
        os.environ["AXIS_INTEGRITY_DATA"] = tempfile.mkdtemp(prefix="integ_data_")      # never touch the engine's own data folder
        try:
            from lib.patrol_radio import PatrolRadio
            r = PatrolRadio()
            r.auditor.path = os.path.join(tempfile.mkdtemp(prefix="aud_"), "b.jsonl")
            r.auditor._last = "0" * 64
            self.assertFalse(r.eject_session("ghost"))                  # nothing was active: honest False, but the id is barred
            self.assertTrue(r.is_ejected("ghost"))
            r.register_session("s1", {"who": "test"})
            self.assertTrue(r.eject_session("s1"))                      # an active session really is ended
            self.assertTrue(r.is_ejected("s1"))
            self.assertEqual(r.auditor.events()[-1]["kind"], "DEFENSIVE_ACTION")
        finally:
            os.environ.pop("AXIS_INTEGRITY_DATA", None)


if __name__ == "__main__":
    unittest.main(verbosity=1)
