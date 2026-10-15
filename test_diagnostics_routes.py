"""test_diagnostics_routes.py - the Boiler Room through the REAL server routes (Flask test client, temp UI folder): the live overview, the engine drill-down, and the
system-locked conversation of Diagnostic mode. Run: python test_diagnostics_routes.py"""
import os
import shutil
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="diagroutes_")
os.environ["NEXXUS_ADMIN_TOKEN"] = "throwaway-admin"
os.environ["NEXXUS_GOVERNANCE_SECRET"] = "throwaway-secret"
os.environ["NEXXUS_UI_ROOT"] = os.path.join(TMP, "ui")
os.environ["NEXXUS_ENGINE_STAGING"] = os.path.join(TMP, "staging", "engines")
os.environ["NEXXUS_ENGINE_LEDGER"] = os.path.join(TMP, "ledger.jsonl")
os.environ["NEXXUS_NOTIFICATIONS_FILE"] = os.path.join(TMP, "notifs.json")
os.environ["NEXXUS_PERIMETER_DIR"] = os.path.join(os.environ.get("TEMP", "."), "nexxus_test_perimeter_" + str(os.getpid()))
os.environ["NEXXUS_DISABLE_AUTOSCHEDULER"] = "1"
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import python_server as srv  # noqa: E402


class Boiler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()
        cls.seen_prompts = []
        cls._orig = srv._invoke_nexxus_pipeline
        srv._invoke_nexxus_pipeline = lambda text: (cls.seen_prompts.append(text) or ("model reply", {}))
        srv._telemetry.ping_all()

    @classmethod
    def tearDownClass(cls):
        srv._invoke_nexxus_pipeline = cls._orig
        srv._mode_state.set("conversation")
        shutil.rmtree(TMP, ignore_errors=True)

    def mode(self, m):
        return self.http.post("/api/mode", json={"mode": m}).get_json()

    def say(self, text):
        return self.http.post("/command-dispatch", json={"command": text}).get_json()

    def test_1_the_overview_has_everything_and_nothing_secret(self):
        r = self.http.get("/api/diagnostics/overview")
        self.assertEqual(r.status_code, 200)
        ov = r.get_json()
        for k in ("infrastructure", "bridge", "engines", "services", "events", "summary"):
            self.assertIn(k, ov)
        groups = {e["group"] for e in ov["engines"]}
        self.assertIn("mesh", groups)
        self.assertGreaterEqual(sum(1 for e in ov["engines"] if e["group"] == "mesh"), 20)         # the 21 mesh engines are listed, whether or not they heartbeat
        self.assertIn("cpu_percent", ov["infrastructure"])
        self.assertEqual({p["label"] for p in ov["bridge"]["ports"]}, {"NEXXUS server", "gateway", "Ollama"})
        text = str(ov).lower()
        for secret in ("throwaway-admin", "throwaway-secret"):
            self.assertNotIn(secret, text)

    def test_2_the_drilldown_works_for_a_known_engine_and_refuses_junk(self):
        d = self.http.get("/api/diagnostics/engine/axis-core").get_json()
        self.assertEqual((d["status"], d["group"], d["name"]), ("success", "mesh", "axis-core"))
        self.assertIn(d["engine_status"], ("heartbeat", "stale", "no-heartbeat", "missing"))
        self.assertIn("facts", d)
        self.assertEqual(self.http.get("/api/diagnostics/engine/no-such-engine").status_code, 404)
        self.assertEqual(self.http.get("/api/diagnostics/engine/..%2f..%2fetc").status_code, 404)
        self.assertEqual(self.http.get("/api/diagnostics/engine/bad name!").status_code, 400)

    def test_3_in_diagnostic_mode_off_topic_conversation_is_locked_out(self):
        self.assertEqual(self.mode("diagnostic")["mode"], "diagnostic")
        before = len(self.seen_prompts)
        r = self.say("tell me a joke about cats")
        self.assertTrue(r.get("halted"))
        self.assertEqual(r["mode_required"]["reason"], "off_topic_in_diagnostic_mode")
        self.assertEqual(len(self.seen_prompts), before)                                            # the model was never asked
        self.assertEqual(self.say("hi there")["mode_required"]["reason"], "off_topic_in_diagnostic_mode")

    def test_4_system_questions_are_answered_from_live_data(self):
        self.mode("diagnostic")
        before = len(self.seen_prompts)
        r = self.say("give me a status overview")
        self.assertIn("Overall:", r["response"])
        self.assertEqual(r["diagnostic"]["source"], "live data")
        r = self.say("how much cpu and memory")
        self.assertIn("CPU", r["response"])
        r = self.say("status of axis-core")
        self.assertIn("axis-core (mesh engine)", r["response"])
        self.assertEqual(len(self.seen_prompts), before)                                            # all three came from data, with no model call

    def test_5_what_the_data_cannot_answer_goes_to_the_model_with_facts_and_a_leash(self):
        self.mode("diagnostic")
        r = self.say("explain the metrics")
        self.assertEqual(r["diagnostic"]["source"], "model, with live facts")
        prompt = self.seen_prompts[-1]
        for needle in ("DIAGNOSTIC MODE", "ONLY about the system", "LIVE FACTS", "QUESTION: explain the metrics"):
            self.assertIn(needle, prompt)

    def test_6_leaving_the_mode_lifts_the_lock(self):
        self.mode("diagnostic")
        self.assertTrue(self.say("tell me a joke").get("halted"))
        self.mode("conversation")
        r = self.say("tell me a joke")
        self.assertFalse(r.get("halted"))
        self.assertEqual(r.get("response"), "model reply")

    def test_7_build_orders_are_still_refused_in_diagnostic_mode(self):
        self.mode("diagnostic")
        r = self.say("build me a landing page for the bridge")
        self.assertTrue(r.get("halted"))
        self.assertNotEqual(r["mode_required"]["reason"], "off_topic_in_diagnostic_mode")


if __name__ == "__main__":
    unittest.main(verbosity=1)
