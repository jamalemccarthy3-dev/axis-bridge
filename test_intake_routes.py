"""test_intake_routes.py - the intake pipeline through the real server: the briefing carries the pipeline summary, the private note is served (never sent), every run is a Flight
Record with a checkpoint per stage, and a blocked asset raises a notification. Run: python test_intake_routes.py"""
import atexit
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="intake_routes_")
atexit.register(shutil.rmtree, TMP, True)
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "cr"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"),
                  NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"), NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1")
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import python_server as srv  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
SNAGGY = 'def slugify(text):\n    """Make a url slug."""\n    return text.strip().lower().replace(" ", "-")\n\ndef shout(text)\n    """Upper-case it."""\n    return text.upper()\n'


def fetcher_for(files):
    def fetch(owner, repo, ref, dest):
        s = Path(dest) / "source"
        s.mkdir()
        out = []
        for p, t in files.items():
            (s / p).write_bytes(t.encode())
            out.append({"path": p, "size": len(t.encode()), "sha256": hashlib.sha256(t.encode()).hexdigest()})
        return {"owner": owner, "repo": repo, "ref": "main", "commit": "abcdef1234567890" * 2 + "abcdef12", "archive_sha256": "0" * 64, "license_spdx": "mit", "license_name": "MIT License",
                "description": "d", "url": "https://github.com/%s/%s" % (owner, repo), "files": out, "skipped": {}}
    return fetch


class Intake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()

    def test_1_the_briefing_carries_the_pipeline_and_the_note_is_served_not_sent(self):
        b = srv._tools.stage("acme", "textkit", None, fetcher=fetcher_for({"textkit.py": SNAGGY}))
        got = self.http.get("/api/ingest/" + b["id"], headers=ADMIN).get_json()["briefing"]
        self.assertEqual(got["pipeline"]["verdict"], "pass")
        self.assertEqual(got["pipeline"]["fixes"], 1)
        text = srv._briefing_text(got)
        self.assertIn("Intake pipeline (Inspect, Heal, Gate, Contribute): axis gate PASS", text)
        self.assertIn("upstream files are kept untouched", text)
        self.assertIn("NEXXUS has not sent it and never will", text)
        self.assertEqual(self.http.get("/api/ingest/%s/contribution" % b["id"]).status_code, 401)
        note = self.http.get("/api/ingest/%s/contribution" % b["id"], headers=ADMIN).get_json()
        self.assertIn("strictly in private", note["letter"])
        self.assertIn("The route forward", note["letter"])
        self.assertFalse(note["sent"])
        self.assertTrue(note["needs_owner_confirmation"])
        self.assertEqual(self.http.get("/api/ingest/nope-such/contribution", headers=ADMIN).status_code, 404)

    def test_2_every_run_is_a_flight_record_with_a_checkpoint_per_stage(self):
        rows = [r for r in self.http.get("/api/link/log", headers=ADMIN).get_json()["rows"] if r["kind"] == "intake"]
        self.assertTrue(rows)
        v = self.http.get("/api/link/txn/" + rows[-1]["flight"], headers=ADMIN).get_json()
        events = [h["event"] for h in v["txn"]["hop_list"]]
        self.assertEqual(events, ["intake_inspect", "intake_heal", "intake_gate", "intake_contribute"])
        self.assertEqual(v["diagnosis"]["verdict"], "completed")
        self.assertIn("intake pipeline", v["plain"])

    def test_3_a_blocked_asset_is_a_blocked_flight_and_raises_a_notification(self):
        with self.assertRaises(srv._tools.VaultError):
            srv._tools.stage("acme", "brokenkit", None, fetcher=fetcher_for({"brokenkit.py": "def (:\n  ???\n"}))
        rows = [r for r in self.http.get("/api/link/log", headers=ADMIN).get_json()["rows"] if r["kind"] == "intake" and r["status"] == "blocked"]
        self.assertTrue(rows)
        v = self.http.get("/api/link/txn/" + rows[-1]["flight"], headers=ADMIN).get_json()
        self.assertEqual(v["diagnosis"]["verdict"], "refused")
        self.assertEqual(v["diagnosis"]["where"], "intake: heal (intake_heal)")                       # the first checkpoint that failed: the corrections ran out
        self.assertIn("did not parse", v["diagnosis"]["reason"])
        orig = srv._tools.stage
        srv._tools.stage = lambda *a, **k: (_ for _ in ()).throw(srv._tools.VaultError("The axis gate blocked this asset (every file parses: broken.py). Nothing was staged."))
        try:
            out = {}
            srv._ingest_worker("acme", "brokenkit", None, out)
        finally:
            srv._tools.stage = orig
        self.assertIn("axis gate blocked", out["error"])
        items = srv._notes.list().get("items", srv._notes.list().get("notifications", []))
        self.assertTrue(any(n["title"].startswith("Blocked at the axis gate") for n in items))


if __name__ == "__main__":
    unittest.main(verbosity=1)
