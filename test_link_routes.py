"""test_link_routes.py - AXIS LINK through the REAL server routes (Flask test client, temp folders): chats and mesh calls land in the ledger, the contents are admin-gated and
redacted, the inspector views and the analyst/hypothesis endpoints answer, and the two-slot input queue turns a third input away. Run: python test_link_routes.py"""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

TMP = tempfile.mkdtemp(prefix="linkroutes_")
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

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}


class Link(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()
        cls.prompts = []
        cls.delay = 0.0
        cls._orig = srv._invoke_nexxus_pipeline

        def fake(text):
            cls.prompts.append(text)
            time.sleep(cls.delay)
            return "model reply", {}
        srv._invoke_nexxus_pipeline = fake

    @classmethod
    def tearDownClass(cls):
        srv._invoke_nexxus_pipeline = cls._orig
        srv._mode_state.set("conversation")
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        self.delay = 0.0
        self.__class__.delay = 0.0

    def test_1_a_chat_is_recorded_with_its_steps_and_the_log_needs_the_token(self):
        r = self.http.post("/command-dispatch", json={"command": "hello there"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.http.get("/api/link/log").status_code, 401)
        rows = self.http.get("/api/link/log", headers=ADMIN).get_json()["rows"]
        chats = [x for x in rows if x["kind"] == "chat"]
        self.assertTrue(chats)
        last = chats[-1]
        self.assertEqual(last["status"], "ok")
        self.assertIn("hello there", last["summary"])
        view = self.http.get("/api/link/txn/" + last["id"], headers=ADMIN).get_json()
        events = [h["event"] for h in view["txn"]["hop_list"]]
        for e in ("received", "queue_wait", "mode_gate", "replied"):
            self.assertIn(e, events)
        self.assertIn("HOPS", view["terminal"])
        self.assertIn("What happened", view["layman"])
        self.assertTrue(view["touchpoints"])

    def test_2_a_bad_signature_on_the_mesh_is_recorded_as_refused(self):
        r = self.http.post("/api/mesh/message", json={"engine": "picthis", "to": "nexxus", "kind": "x", "signature": "nope"})
        self.assertEqual(r.status_code, 401)
        rows = self.http.get("/api/link/log", headers=ADMIN).get_json()["rows"]
        refused = [x for x in rows if x["kind"] == "mesh_message" and x["status"] == "blocked"]
        self.assertTrue(refused)
        t = self.http.get("/api/link/txn/" + refused[-1]["id"], headers=ADMIN).get_json()["txn"]
        self.assertTrue(any(h["check"] == "signature" and h["status"] == "failed" for h in t["hop_list"]))
        self.assertNotIn("nope", str(t))                                            # the signature value itself is redacted

    def test_3_nothing_secret_leaks_through_any_link_view(self):
        self.http.post("/api/mesh/message", json={"engine": "picthis", "password": "hunter2-secret", "signature": "sig-abc"})
        everything = str(self.http.get("/api/link/log?quiet=1", headers=ADMIN).get_json())
        for row in self.http.get("/api/link/log?quiet=1", headers=ADMIN).get_json()["rows"]:
            everything += str(self.http.get("/api/link/txn/" + row["id"], headers=ADMIN).get_json())
        for secret in ("hunter2-secret", "sig-abc", "throwaway-admin", "throwaway-secret"):
            self.assertNotIn(secret, everything)

    def test_4_unknown_transaction_and_bad_ids(self):
        self.assertEqual(self.http.get("/api/link/txn/t999999", headers=ADMIN).status_code, 404)
        self.assertEqual(self.http.get("/api/link/txn/..%2Fetc", headers=ADMIN).status_code, 404)

    def test_5_analyze_gives_the_exact_part_at_once_and_the_model_part_by_job(self):
        self.http.post("/command-dispatch", json={"command": "another one"})
        tid = [x for x in self.http.get("/api/link/log", headers=ADMIN).get_json()["rows"] if x["kind"] == "chat"][-1]["id"]
        self.assertEqual(self.http.post("/api/link/analyze", json={"txn": tid, "element": "speed"}).status_code, 401)
        r = self.http.post("/api/link/analyze", json={"txn": tid, "element": "speed"}, headers=ADMIN).get_json()
        self.assertIn("How fast", r["rules"])
        for _ in range(50):
            j = self.http.get("/api/link/job/" + r["job"], headers=ADMIN).get_json()
            if j["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(j["state"], "done")
        self.assertEqual(j["text"], "model reply")
        self.assertTrue(any("AXIS LINK ANALYST" in p for p in self.prompts))
        bad = self.http.post("/api/link/analyze", json={"txn": tid, "element": "nonsense"}, headers=ADMIN)
        self.assertEqual(bad.status_code, 400)

    def test_6_hypothesis_is_measured_before_the_model_speaks(self):
        r = self.http.post("/api/link/hypothesis", json={"text": "picthis is slow and keeps failing"}, headers=ADMIN).get_json()
        self.assertIn("evidence", r)
        self.assertIn("LEDGER", r["evidence"]["facts"])
        self.assertEqual(self.http.post("/api/link/hypothesis", json={"text": "  "}, headers=ADMIN).status_code, 400)

    def test_7_the_third_input_is_turned_away_and_nothing_is_lost(self):
        self.__class__.delay = 0.6
        results = []

        def send(i):
            results.append((i, self.http.post("/command-dispatch", json={"command": "msg %d" % i}).status_code))
        a = threading.Thread(target=send, args=(1,)); a.start(); time.sleep(0.15)
        b = threading.Thread(target=send, args=(2,)); b.start(); time.sleep(0.15)
        snap = self.http.get("/api/input/queue").get_json()
        self.assertEqual(snap["state"], "full")
        c = self.http.post("/command-dispatch", json={"command": "msg 3"})
        self.assertEqual(c.status_code, 429)
        self.assertTrue(c.get_json()["busy"])
        a.join(); b.join()
        self.assertEqual(sorted(results), [(1, 200), (2, 200)])                     # the two in line were both answered, in order
        after = self.http.get("/api/input/queue").get_json()
        self.assertEqual(after["state"], "idle")
        self.assertGreaterEqual(after["turned_away"], 1)
        self.assertEqual(self.http.post("/command-dispatch", json={"command": "msg 4"}).status_code, 200)   # a slot is free again

    def test_8_link_mode_answers_with_the_ledger_numbers(self):
        self.assertEqual(self.http.post("/api/mode", json={"mode": "link"}).get_json().get("mode"), "link")
        self.http.post("/command-dispatch", json={"command": "how busy has the picthis route been"})
        self.assertTrue(any("AXIS LINK MODE" in p and "LEDGER" in p for p in self.prompts))
        self.http.post("/api/mode", json={"mode": "conversation"})

    def test_10_a_chat_is_visible_in_flight_and_findable_by_flight_id(self):
        self.__class__.delay = 0.8
        th = threading.Thread(target=lambda: self.http.post("/command-dispatch", json={"command": "a slow question about nothing"}))
        th.start()
        time.sleep(0.3)
        rows = [x for x in self.http.get("/api/link/log", headers=ADMIN).get_json()["rows"] if x["kind"] == "chat" and x["status"] == "pending"]
        self.assertTrue(rows, "the chat should be in the ledger while it is still being answered")
        fid = rows[-1]["flight"]
        self.assertRegex(fid, r"^FL-[0-9A-Z]+-\d{4}$")
        mid = self.http.get("/api/link/txn/" + fid, headers=ADMIN).get_json()
        self.assertEqual(mid["diagnosis"]["verdict"], "in flight")
        self.assertIn("input queue", mid["diagnosis"]["where"])
        th.join()
        done = self.http.get("/api/link/txn/" + fid, headers=ADMIN).get_json()
        self.assertEqual(done["txn"]["status"], "ok")
        self.assertEqual(done["diagnosis"]["verdict"], "completed")
        self.assertEqual(self.http.get("/api/link/txn/FL-ZZZZ-0000", headers=ADMIN).status_code, 404)

    def test_11_replies_never_carry_nan_or_infinity(self):
        with srv.app.test_request_context():
            body = srv.jsonify({"latency": float("nan"), "p95": float("inf"), "ok": 1.5, "nested": [{"x": -float("inf")}]}).get_data(as_text=True)
        self.assertNotIn("NaN", body)
        self.assertNotIn("nfinity", body)
        import json
        d = json.loads(body, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))      # strict parse: a bare NaN would raise
        self.assertEqual((d["latency"], d["p95"], d["ok"], d["nested"][0]["x"]), (None, None, 1.5, None))

    def test_9_a_module_call_is_recorded_hop_by_hop_and_pings_are_quiet(self):
        t0 = time.time()
        srv._module_txn({"name": "picthis", "packet": {"op": "call", "signature": "zzz"}, "ok": True, "error": None, "t_start": t0, "t_sent": t0 + 0.001, "t_end": t0 + 0.05, "http": 200})
        srv._module_txn({"name": "picthis", "packet": {"op": "health"}, "ok": True, "error": None, "t_start": t0, "t_sent": t0 + 0.001, "t_end": t0 + 0.01, "http": 200})
        shown = [x for x in self.http.get("/api/link/log", headers=ADMIN).get_json()["rows"] if x["kind"] == "module_rpc"]
        self.assertTrue(shown)
        self.assertFalse(any("health" in x["summary"] for x in shown))
        quiet = [x for x in self.http.get("/api/link/log?quiet=1", headers=ADMIN).get_json()["rows"] if x["kind"] == "module_rpc" and "health" in x["summary"]]
        self.assertTrue(quiet)
        t = self.http.get("/api/link/txn/" + shown[-1]["id"], headers=ADMIN).get_json()["txn"]
        self.assertEqual([h["event"] for h in t["hop_list"]], ["signed_request", "sent_to_gateway", "gateway_module"])
        self.assertAlmostEqual(t["duration_ms"], 50, delta=5)
        self.assertNotIn("zzz", str(t))


if __name__ == "__main__":
    unittest.main(verbosity=1)
