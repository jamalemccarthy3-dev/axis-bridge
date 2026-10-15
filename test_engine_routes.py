"""test_engine_routes.py - Engine Build Mode, telemetry and the Prompt Recipe Vault through the REAL server routes (Flask test client, throwaway token, temp UI folder,
fake model). Nothing is deployed to the real UI directory. Run: python test_engine_routes.py"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="engroutes_")
os.environ["NEXXUS_ADMIN_TOKEN"] = "throwaway-admin"
os.environ["NEXXUS_GOVERNANCE_SECRET"] = "throwaway-secret"
os.environ["NEXXUS_UI_ROOT"] = os.path.join(TMP, "ui")
os.environ["NEXXUS_ENGINE_STAGING"] = os.path.join(TMP, "staging", "engines")
os.environ["NEXXUS_ENGINE_LEDGER"] = os.path.join(TMP, "ledger.jsonl")
os.environ["NEXXUS_PROMPT_RECIPES"] = os.path.join(TMP, "prompt_recipes.json")
os.environ["NEXXUS_NOTIFICATIONS_FILE"] = os.path.join(TMP, "notifs.json")
os.environ["NEXXUS_PERIMETER_DIR"] = os.path.join(os.environ.get("TEMP", "."), "nexxus_test_perimeter_" + str(os.getpid()))
os.environ["NEXXUS_DISABLE_AUTOSCHEDULER"] = "1"
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import python_server as srv  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
CORE = '''def describe():
    return {"name": "word counter", "purpose": "Counts words.", "inputs": {"text": "text"}, "example": {"text": "a b c"}}


def run(payload):
    t = payload.get("text")
    if not isinstance(t, str):
        raise ValueError("text must be a string")
    return {"status": "success", "words": len(t.split())}
'''
TEST = '''from engine.core import run
assert run({"text": "a b c"})["words"] == 3
try:
    run({})
    raise SystemExit("bad input was accepted")
except ValueError:
    pass
'''


def fake_model(messages):
    return "### FILE: engine/core.py\n```python\n%s```\n### FILE: test_core.py\n```python\n%s```\n" % (CORE, TEST)


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()
        cls.eb = srv._eb
        cls.eb._default_generate = fake_model                       # the model is replaced; everything else is real
        cls.eb.MAP_ROOTS = [cls.eb.UI_ROOT]                          # map the temp folder, not the whole workspace, to keep the test quick
        srv._engine_cfg["standalone"] = True

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def get(self, path):
        return self.http.get(path)

    def post(self, path, body=None, admin=False):
        return self.http.post(path, json=body or {}, headers=ADMIN if admin else {})

    def wait_for(self, bid, want=("staged", "failed", "needs_model"), timeout=90):
        end = time.time() + timeout
        while time.time() < end:
            st = self.get("/api/engine/builds/" + bid).get_json()["build"]["status"]
            if st in want:
                return st
            time.sleep(0.3)
        self.fail("the build never finished")

    def test_1_a_build_needs_the_engine_build_mode(self):
        self.post("/api/mode", {"mode": "conversation"})
        r = self.post("/api/engine/builds", {"request": "Build an engine that counts words in a text"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["status"], "halted")
        halted = self.post("/command-dispatch", {"command": "build an engine that counts words in some text"}).get_json()
        self.assertTrue(halted.get("halted"))                                                # Conversation mode still halts build orders

    def test_2_the_standalone_switch(self):
        self.assertTrue(self.get("/api/engine/config").get_json()["standalone"])
        self.assertEqual(self.post("/api/engine/config", {"standalone": "yes"}).status_code, 400)
        self.assertFalse(self.post("/api/engine/config", {"standalone": False}).get_json()["standalone"])
        self.assertTrue(self.post("/api/engine/config", {"standalone": True}).get_json()["standalone"])

    def test_3_chat_to_staged_to_approved_to_deployed(self):
        self.post("/api/mode", {"mode": "engine_build"})
        self.post("/api/engine/config", {"standalone": False})                              # linked this time
        r = self.post("/command-dispatch", {"command": "Build an engine that counts the words in a text"}).get_json()
        self.assertIn("Engine build started", r["response"])
        bid = r["engine_build"]["id"]
        self.assertEqual(r["engine_build"]["mode"], "linked")
        self.assertEqual(self.wait_for(bid), "staged")
        ev = self.get("/api/engine/builds/%s/events?since=0" % bid).get_json()
        self.assertIn("phase", [e["kind"] for e in ev["events"]])
        paths = {f["path"]: f for f in ev["tree"]["files"]}
        self.assertEqual(paths["engine/core.py"]["state"], "tested")
        self.assertEqual(paths["nexxus_link.py"]["origin"], "template")
        self.assertEqual(self.get("/api/engine/builds/%s/events?since=%d" % (bid, ev["events"][-1]["seq"])).get_json()["events"], [])
        f = self.get("/api/engine/builds/%s/file?path=engine/core.py" % bid).get_json()
        self.assertIn("def run", f["text"])
        self.assertEqual(self.get("/api/engine/builds/%s/file?path=../build.json" % bid).status_code, 404)
        brief = self.get("/api/engine/builds/%s/briefing" % bid).get_json()["briefing"]
        self.assertEqual(brief["mode"], "linked")
        name = brief["name"]
        self.assertFalse(Path(os.environ["NEXXUS_UI_ROOT"], name).exists())                  # staged, NOT deployed
        # approval needs the admin token, the confirm word, and the hash that was shown
        self.assertEqual(self.post("/api/engine/builds/%s/approve" % bid, {"confirm": bid}).status_code, 401)
        self.assertEqual(self.post("/api/engine/builds/%s/approve" % bid, {"briefing_sha256": brief["sha256"]}, admin=True).status_code, 400)
        self.assertEqual(self.post("/api/engine/builds/%s/approve" % bid, {"confirm": bid, "briefing_sha256": "0" * 64}, admin=True).status_code, 409)
        self.assertFalse(Path(os.environ["NEXXUS_UI_ROOT"], name).exists())
        ok = self.post("/api/engine/builds/%s/approve" % bid, {"confirm": bid, "briefing_sha256": brief["sha256"]}, admin=True)
        self.assertEqual(ok.status_code, 200, ok.get_json())
        folder = Path(os.environ["NEXXUS_UI_ROOT"], name)
        self.assertTrue((folder / "module.json").is_file() and (folder / "nexxus.secret").is_file())
        self.assertEqual(self.get("/api/engine/builds/%s" % bid).get_json()["build"]["status"], "deployed")
        self.assertEqual(self.post("/api/engine/builds/%s/approve" % bid, {"confirm": bid, "briefing_sha256": brief["sha256"]}, admin=True).status_code, 409)
        # a deployed engine is registered for telemetry on the next refresh, and the deployment was announced
        snap = self.post("/api/telemetry/ping").get_json()
        self.assertIn(name, [e["name"] for e in snap["engines"]])
        entry = next(e for e in snap["engines"] if e["name"] == name)
        self.assertTrue(entry["linked"])
        self.assertIn("deployed", [(e["engine"], e["kind"]) [1] for e in snap["events"] if e["engine"] == name])
        self.assertTrue(self.eb.verify_ledger()[0])

    def test_4_reject_needs_the_token_and_deploys_nothing(self):
        self.post("/api/mode", {"mode": "engine_build"})
        self.post("/api/engine/config", {"standalone": True})
        bid = self.post("/api/engine/builds", {"request": "Build an engine that counts words for reports"}).get_json()["id"]
        self.assertEqual(self.wait_for(bid), "staged")
        self.assertEqual(self.post("/api/engine/builds/%s/reject" % bid, {"confirm": bid}).status_code, 401)
        r = self.post("/api/engine/builds/%s/reject" % bid, {"confirm": bid}, admin=True)
        self.assertEqual(r.get_json()["status"], "success")
        listed = {b["id"]: b["status"] for b in self.get("/api/engine/builds").get_json()["builds"]}
        self.assertEqual(listed[bid], "rejected")
        self.assertEqual(self.get("/api/engine/builds/nope").status_code, 404)

    def test_5_the_workspace_map_is_summarised_without_bodies(self):
        m = self.get("/api/engine/map?refresh=1").get_json()
        self.assertEqual(m["status"], "success")
        self.assertIn("py_files", m["counts"])
        self.assertNotIn("def run", json.dumps(m))

    def test_6_telemetry_feed_collects_mesh_and_module_activity(self):
        tel = srv._telemetry
        before = self.get("/api/telemetry").get_json()["latest_seq"]
        tel.record("axis-logic", "message", "hello")
        srv._ext._rpc  # the hook is installed on the real external-call function
        self.assertIsNotNone(srv._ext.ACTIVITY_HOOK)
        srv._ext.ACTIVITY_HOOK("picthis", "call", True)
        srv._ext.ACTIVITY_HOOK("picthis", "health", True)                                      # its own health pings are not activity
        ev = self.get("/api/telemetry?since=%d" % before).get_json()["events"]
        self.assertEqual([(e["engine"], e["kind"]) for e in ev], [("axis-logic", "message"), ("picthis", "rpc")])
        self.assertTrue(all(e["beep"] for e in ev))

    def test_7_the_prompt_vault(self):
        d = self.get("/api/prompts").get_json()
        self.assertGreaterEqual(len(d["recipes"]), 8)
        self.assertTrue(all(r["builtin"] for r in d["recipes"]))
        good = {"title": "My weekly report", "prompt": "Build an engine that makes a weekly report from [DATA] with the three biggest changes.", "category": "Engine", "mode": "engine_build"}
        self.assertEqual(self.post("/api/prompts", good).status_code, 401)                      # saving a recipe is yours to do: needs the token
        r = self.post("/api/prompts", good, admin=True)
        self.assertEqual(r.status_code, 201)
        rid = r.get_json()["recipe"]["id"]
        self.assertIn(rid, [x["id"] for x in self.get("/api/prompts").get_json()["recipes"]])
        self.assertEqual(self.post("/api/prompts", dict(good, title="x"), admin=True).status_code, 400)
        self.assertEqual(self.http.delete("/api/prompts/" + rid).status_code, 401)
        self.assertEqual(self.http.delete("/api/prompts/engine-standalone-module", headers=ADMIN).status_code, 400)
        self.assertEqual(self.http.delete("/api/prompts/" + rid, headers=ADMIN).status_code, 200)
        self.assertEqual(self.http.delete("/api/prompts/" + rid, headers=ADMIN).status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=1)
