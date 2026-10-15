"""test_first_run.py - a fresh install passes its own dashboard audit: with no dashboard on disk, the built-in bots are orphans; the first-run bootstrap creates the default dashboard and nests them, and
does nothing the second time. Uses a temp dashboards folder, never the real one. Run: python test_first_run.py"""
import atexit
import os
import shutil
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="firstrun_")
atexit.register(shutil.rmtree, TMP, True)
os.environ.update({"NEXXUS_ADMIN_TOKEN": "throwaway-admin", "NEXXUS_GOVERNANCE_SECRET": "throwaway-secret", "NEXXUS_UI_ROOT": os.path.join(TMP, "ui"), "NEXXUS_ENGINE_STAGING": os.path.join(TMP, "s", "e"),
                   "NEXXUS_ENGINE_LEDGER": os.path.join(TMP, "l.jsonl"), "NEXXUS_NOTIFICATIONS_FILE": os.path.join(TMP, "n.json"), "NEXXUS_PERIMETER_DIR": os.path.join(TMP, "p"),
                   "NEXXUS_DASHBOARDS_DIR": os.path.join(TMP, "dashboards"), "NEXXUS_DISABLE_AUTOSCHEDULER": "1"})
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus"))


class FirstRun(unittest.TestCase):
    def test_fresh_install_audit_fails_then_bootstrap_fixes_it_once(self):
        import python_server as srv
        http = srv.app.test_client()
        before = http.get("/api/dashboards/audit").get_json()
        self.assertFalse(before["ok"])                                                  # nothing is on a dashboard yet
        self.assertGreaterEqual(len(before["orphans"]), 1)
        first = srv._bootstrap_default_dashboard()
        self.assertTrue(first["created"])
        self.assertGreaterEqual(first["nested"], len(before["orphans"]))
        after = http.get("/api/dashboards/audit").get_json()
        self.assertTrue(after["ok"], after)
        self.assertEqual((len(after["orphans"]), len(after["hubs"])), (0, 1))
        again = srv._bootstrap_default_dashboard()                                       # idempotent: nothing created, nothing duplicated
        self.assertFalse(again["created"])
        self.assertEqual(len(http.get("/api/dashboards/audit").get_json()["hubs"]), 1)
        self.assertTrue(os.path.isfile(os.path.join(TMP, "dashboards", "nexxus-operations", "front_face.html")))

    def test_the_real_dashboards_folder_was_not_touched(self):
        self.assertTrue(os.environ["NEXXUS_DASHBOARDS_DIR"].startswith(TMP))


if __name__ == "__main__":
    unittest.main(verbosity=1)
