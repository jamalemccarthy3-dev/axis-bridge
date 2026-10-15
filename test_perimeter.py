"""test_perimeter.py - the perimeter overrides: the Perimeter class itself, then through the REAL server routes (Flask test client, temp folders): breach events from a bad
signature, redacted quarantine, Hard Lock enforced on the mesh and on module calls, the triad board, the notification, and the unlock-dialog token check.
Run: python test_perimeter.py"""
import atexit
import os
import shutil
import sys
import tempfile
import time
import unittest

TMP = tempfile.mkdtemp(prefix="perimeter_")
os.environ["NEXXUS_ADMIN_TOKEN"] = "throwaway-admin"
os.environ["NEXXUS_GOVERNANCE_SECRET"] = "throwaway-secret"
os.environ["NEXXUS_UI_ROOT"] = os.path.join(TMP, "ui")
os.environ["NEXXUS_ENGINE_STAGING"] = os.path.join(TMP, "staging", "engines")
os.environ["NEXXUS_ENGINE_LEDGER"] = os.path.join(TMP, "ledger.jsonl")
os.environ["NEXXUS_NOTIFICATIONS_FILE"] = os.path.join(TMP, "notifs.json")
os.environ["NEXXUS_PERIMETER_DIR"] = os.path.join(TMP, "perim")
os.environ["NEXXUS_DISABLE_AUTOSCHEDULER"] = "1"
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus"))

import perimeter  # noqa: E402
import python_server as srv  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
atexit.register(shutil.rmtree, TMP, True)


class Unit(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="perim_unit_", dir=TMP)
        self.now = [1000.0]
        self.seen = []
        self.p = perimeter.Perimeter(self.dir, clock=lambda: self.now[0], on_breach=self.seen.append)

    def test_lock_unlock_and_persistence(self):
        self.p.lock("picthis", "testing")
        self.assertIn("Hard Lock", self.p.blocked_reason("picthis"))
        self.assertIsNone(self.p.blocked_reason("axis-core"))
        again = perimeter.Perimeter(self.dir)                                    # survives a restart
        self.assertIsNotNone(again.locked("picthis"))
        self.p.unlock("picthis")
        self.assertIsNone(self.p.locked("picthis"))
        with self.assertRaises(perimeter.PerimeterError):
            self.p.unlock("picthis")
        for bad in ("", "../x", "a b", "x" * 80):
            with self.assertRaises(perimeter.PerimeterError):
                self.p.lock(bad)

    def test_breach_repeats_count_once_and_a_lock_does_not_flash(self):
        a = self.p.breach("bad-signature", "picthis", "x", severity="alert")
        self.now[0] += 1
        b = self.p.breach("bad-signature", "picthis", "x", severity="alert")
        self.assertEqual((a["seq"], b["seq"], b["count"]), (1, 1, 2))
        self.assertEqual(len(self.seen), 1)                                      # one notification, not two
        self.assertTrue(self.p.summary()["alert"])
        self.p.ack()
        self.assertFalse(self.p.summary()["alert"])
        self.now[0] += 60
        self.p.breach("bad-signature", "picthis", "x", severity="alert")
        self.assertEqual(self.p.summary()["breach_seq"], 2)
        self.p.ack()
        self.p.lock("axis-core", "me")                                           # your own override is logged but does not flash
        self.assertFalse(self.p.summary()["alert"])

    def test_quarantine_is_inert_redacted_and_releasable(self):
        qid = self.p.quarantine("picthis", "bad", {"engine": "picthis", "signature": "sig-xyz", "password": "hunter2", "body": "hello"})
        rec = self.p.quarantine_get(qid)
        self.assertIn("hello", rec["packet"])
        self.assertNotIn("sig-xyz", rec["packet"])
        self.assertNotIn("hunter2", rec["packet"])
        self.assertEqual(len(self.p.quarantined()), 1)
        self.assertNotIn("packet", self.p.quarantined()[0])                       # the list never carries contents
        self.assertIsNone(self.p.quarantine_get("../../etc/passwd"))
        self.p.release(qid)
        self.assertEqual(self.p.quarantined(), [])
        with self.assertRaises(perimeter.PerimeterError):
            self.p.release(qid)


class ReleaseAll(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="perim_relall_", dir=TMP)
        self.p = perimeter.Perimeter(self.dir)

    def test_release_all_flushes_records_first_and_chains(self):
        ids = [self.p.quarantine("n%d" % i, "bad", {"body": "text-%d" % i}) for i in range(4)]
        r = self.p.release_all()
        self.assertEqual((r["released"], r["still_held"], r["failed"]), (4, 0, 0))
        self.assertEqual(self.p.quarantined(), [])
        log = self.p.release_log()
        self.assertTrue(log["ok"])
        self.assertEqual(sorted(x["id"] for x in log["items"]), sorted(ids))
        self.assertNotIn("text-", str(log))
        self.p.quarantine("n9", "bad", {"body": "x"})
        self.p.release_all()
        self.assertEqual(self.p.release_log()["total"], 5)                       # the chain continues across batches
        self.assertTrue(self.p.release_log()["ok"])

    def test_only_listed_ids_and_only_valid_ones(self):
        a, b = self.p.quarantine("a", "r", {}), self.p.quarantine("b", "r", {})
        r = self.p.release_all(ids=[a, a, "../../x", 5, "q0000000000"])
        self.assertEqual(r["ids"], [a])                                          # de-duplicated; junk and unknown ids ignored, never touched on disk
        self.assertEqual((r["still_held"], len(self.p.quarantined())), (1, 1))
        self.assertEqual(self.p.quarantined()[0]["id"], b)

    def test_tampered_record_is_noticed(self):
        for i in range(3):
            self.p.quarantine("n", "r", {})
        self.p.release_all()
        path = os.path.join(self.dir, "released.jsonl")
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines[:1] + lines[2:]) + "\n")                     # a line removed
        self.assertFalse(self.p.release_log()["ok"])

    def test_nothing_is_deleted_if_the_record_cannot_be_written(self):
        qid = self.p.quarantine("n", "r", {})
        os.makedirs(os.path.join(self.dir, "released.jsonl"))                    # a directory where the file should be: the append fails
        with self.assertRaises(OSError):
            self.p.release_all()
        self.assertEqual([i["id"] for i in self.p.quarantined()], [qid])


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()

    def test_1_unlock_dialog_check(self):
        self.assertEqual(self.http.get("/api/auth/check").status_code, 401)
        self.assertEqual(self.http.get("/api/auth/check", headers={"X-Nexxus-Admin-Token": "wrong"}).status_code, 401)
        self.assertEqual(self.http.get("/api/auth/check", headers=ADMIN).get_json()["status"], "success")

    def test_2_bad_signature_is_a_breach_with_a_redacted_quarantined_copy_and_one_notification(self):
        before = self.http.get("/api/perimeter/status").get_json()["perimeter"]["breach_seq"]
        r = self.http.post("/api/mesh/message", json={"engine": "picthis", "to": "nexxus", "kind": "x", "signature": "sig-secret-abc", "body": "forged"})
        self.assertEqual(r.status_code, 401)
        st = self.http.get("/api/perimeter/status").get_json()
        self.assertGreater(st["perimeter"]["breach_seq"], before)
        self.assertTrue(st["perimeter"]["alert"])
        self.assertNotIn("picthis", str(st))                                      # the public numbers carry no node names
        self.assertNotIn("events", st)
        detail = self.http.get("/api/perimeter/status", headers=ADMIN).get_json()
        self.assertEqual(detail["events"][-1]["kind"], "bad-signature")
        q = self.http.get("/api/perimeter/quarantine", headers=ADMIN).get_json()["items"]
        self.assertTrue(q)
        item = self.http.get("/api/perimeter/quarantine/" + q[-1]["id"], headers=ADMIN).get_json()["item"]
        self.assertIn("forged", item["packet"])
        self.assertNotIn("sig-secret-abc", str(item))
        notes = [n for n in srv._notes.list().get("items", srv._notes.list().get("notifications", [])) if n["kind"] == "security"]
        self.assertTrue(notes)
        self.assertEqual(notes[0]["actions"][0]["type"], "open_perimeter")
        self.assertEqual(self.http.get("/api/perimeter/quarantine").status_code, 401)

    def test_3_acknowledging_stops_the_flash(self):
        self.assertEqual(self.http.post("/api/perimeter/ack").status_code, 401)
        self.http.post("/api/perimeter/ack", headers=ADMIN)
        self.assertFalse(self.http.get("/api/perimeter/status").get_json()["perimeter"]["alert"])

    def test_4_hard_lock_refuses_the_node_on_the_mesh_and_unlock_restores_it(self):
        self.assertEqual(self.http.post("/api/perimeter/lock", json={"node": "picthis"}).status_code, 401)
        self.assertEqual(self.http.post("/api/perimeter/lock", json={"node": "../bad"}, headers=ADMIN).status_code, 400)
        self.assertEqual(self.http.post("/api/perimeter/lock", json={"node": "picthis", "reason": "drill"}, headers=ADMIN).status_code, 200)
        r = self.http.post("/api/mesh/status", json={"engine": "picthis", "state": "running"})
        self.assertEqual(r.status_code, 423)                                      # refused before the signature is even looked at
        self.assertIn("Hard Lock", r.get_json()["message"])
        rows = self.http.get("/api/link/log?quiet=1", headers=ADMIN).get_json()["rows"]
        self.assertTrue(any(x["status"] == "blocked" and x["kind"] == "mesh_heartbeat" for x in rows))     # and the ledger shows it as refused
        self.assertEqual(self.http.post("/api/mesh/status", json={"engine": "axis-core", "state": "running"}).status_code, 401)   # another node is untouched (401 = unsigned, not locked)
        nodes = self.http.get("/api/perimeter/triad", headers=ADMIN).get_json()["nodes"]
        self.assertTrue(next(n for n in nodes if n["name"] == "picthis")["locked"])
        self.assertEqual(self.http.post("/api/perimeter/unlock", json={"node": "picthis"}, headers=ADMIN).status_code, 200)
        self.assertEqual(self.http.post("/api/mesh/status", json={"engine": "picthis", "state": "running"}).status_code, 401)   # reachable again (unsigned, so refused for that reason)

    def test_5_hard_lock_stops_module_calls_without_sending_anything(self):
        import nexxus_external as ext
        sent = []
        orig = ext._rpc_inner
        ext._rpc_inner = lambda name, packet, timeout: (sent.append(name) or (True, {"x": 1}))
        try:
            self.http.post("/api/perimeter/lock", json={"node": "demo-mod", "reason": "drill"}, headers=ADMIN)
            ok, out = ext._rpc("demo-mod", {"op": "call"}, 1)
            self.assertFalse(ok)
            self.assertIn("frozen", out)
            self.assertEqual(sent, [])
            self.http.post("/api/perimeter/unlock", json={"node": "demo-mod"}, headers=ADMIN)
            self.assertTrue(ext._rpc("demo-mod", {"op": "call"}, 1)[0])
            self.assertEqual(sent, ["demo-mod"])
        finally:
            ext._rpc_inner = orig

    def test_6_quarantine_a_recorded_transaction_and_release_it(self):
        tid = self.http.get("/api/link/log", headers=ADMIN).get_json()["rows"][-1]["id"]
        r = self.http.post("/api/perimeter/quarantine", json={"txn": tid, "reason": "looks odd"}, headers=ADMIN).get_json()
        self.assertEqual(r["status"], "success")
        self.assertEqual(self.http.post("/api/perimeter/quarantine", json={"txn": "t99999999"}, headers=ADMIN).status_code, 404)
        self.assertEqual(self.http.delete("/api/perimeter/quarantine/" + r["id"], headers=ADMIN).status_code, 200)
        self.assertEqual(self.http.delete("/api/perimeter/quarantine/" + r["id"], headers=ADMIN).status_code, 404)

    def test_6b_release_all_needs_token_and_confirm_and_keeps_unseen_items(self):
        url = "/api/perimeter/quarantine/release-all"
        for n in range(3):
            srv._perim.quarantine("picthis", "drill %d" % n, {"body": "secret-looking-body-%d" % n})
        held = [i["id"] for i in srv._perim.quarantined()]
        self.assertGreaterEqual(len(held), 3)
        self.assertEqual(self.http.post(url, json={"confirm": True}).status_code, 401)                                  # no token
        self.assertEqual(self.http.post(url, json={}, headers=ADMIN).status_code, 400)                                  # no confirm: nothing happens
        self.assertEqual(self.http.post(url, json={"confirm": "yes"}, headers=ADMIN).status_code, 400)
        self.assertEqual(len(srv._perim.quarantined()), len(held))
        self.assertEqual(self.http.post(url, json={"confirm": True, "expected": len(held) + 5}, headers=ADMIN).status_code, 409)   # the count the operator saw is stale
        self.assertEqual(len(srv._perim.quarantined()), len(held))
        late = srv._perim.quarantine("picthis", "arrived while the operator was looking", {"body": "late"})             # lands after the view was drawn
        r = self.http.post(url, json={"confirm": True, "ids": held}, headers=ADMIN).get_json()
        self.assertEqual(r["status"], "success")
        self.assertEqual((r["released"], r["still_held"], r["failed"]), (len(held), 1, 0))
        self.assertEqual([i["id"] for i in srv._perim.quarantined()], [late])                                           # the unseen one is untouched
        self.assertEqual(r["perimeter"]["quarantined"], 1)
        log = self.http.get(url, headers=ADMIN).get_json()["log"]
        self.assertTrue(log["ok"])
        self.assertEqual(log["total"], len(held))
        self.assertNotIn("secret-looking-body", str(log))                                                               # the record never holds packet text
        r2 = self.http.post(url, json={"confirm": True}, headers=ADMIN).get_json()                                      # no ids = everything held now
        self.assertEqual((r2["released"], r2["still_held"]), (1, 0))
        r3 = self.http.post(url, json={"confirm": True}, headers=ADMIN).get_json()                                      # nothing left: success, zero
        self.assertEqual(r3["released"], 0)
        ev = self.http.get("/api/perimeter/status", headers=ADMIN).get_json()["events"]
        self.assertTrue(any(e["kind"] == "quarantine-release-all" for e in ev))

    def test_6c_engines_are_judged_as_a_headless_cluster_not_as_dashboard_widgets(self):
        orig = srv._axis_bridge.telemetry
        live = {"live": {"fresh": True}, "mesh_ready": True, "found": True}
        try:
            srv._axis_bridge.telemetry = lambda: {"engines": {"axis-core": live, "axis-link": live}}      # healthy engines, no dashboard card anywhere
            c = srv._engine_cluster_rollup()
            self.assertEqual((c["members"], c["live"], c["dead_processes"]), (2, 2, []))
            self.assertIn("axis-vision", c["unreferenced_folders"])                                         # a real folder on disk that this fake roster does not list
            self.assertFalse(c["ok"])
            srv._axis_bridge.telemetry = lambda: {"engines": {"axis-core": {"live": {"fresh": False}, "mesh_ready": True}}}
            self.assertEqual(srv._engine_cluster_rollup()["dead_processes"], ["axis-core"])               # a dead process IS an orphan
        finally:
            srv._axis_bridge.telemetry = orig
        d = self.http.get("/api/dashboards/audit").get_json()
        self.assertIn("engine_cluster", d)
        self.assertNotIn("engines_without_card", str(d))                                                    # no card-per-engine rule

    def test_7_triad_board_lists_nodes_with_traffic_and_journeys(self):
        d = self.http.get("/api/perimeter/triad", headers=ADMIN).get_json()
        self.assertGreaterEqual(len(d["nodes"]), 20)
        for k in ("name", "status", "sent", "received", "failed", "locked"):
            self.assertIn(k, d["nodes"][0])
        self.assertIsInstance(d["journeys"], list)
        self.assertNotIn("throwaway-admin", str(d))
        self.assertEqual(self.http.get("/api/perimeter/triad").status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=1)
