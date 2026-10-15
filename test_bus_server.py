"""test_bus_server.py - the orchestrator bus through the REAL server routes (Flask test client, throwaway token, secret and ledger).
Run: python test_bus_server.py"""
import json
import os
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="busrv_")
os.environ["NEXXUS_ADMIN_TOKEN"] = "throwaway-admin"
os.environ["NEXXUS_GOVERNANCE_SECRET"] = "throwaway-secret"
os.environ["NEXXUS_BUS_LEDGER"] = os.path.join(TMP, "ledger.jsonl")
os.environ["NEXXUS_NOTIFICATIONS_FILE"] = os.path.join(TMP, "notifs.json")
os.environ["NEXXUS_PERIMETER_DIR"] = os.path.join(os.environ.get("TEMP", "."), "nexxus_test_perimeter_" + str(os.getpid()))
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import python_server as srv  # noqa: E402
from orchestrator_client import OrchestratorClient  # noqa: E402
from orchestrator_bus import sha256_file  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}


class ThroughTheServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()
        cls.artifact = os.path.join(TMP, "intro.mp4")
        with open(cls.artifact, "wb") as f:
            f.write(b"first cut of the intro")
        post = lambda path, body, headers=None: cls.http.post(path, json=body, headers=headers or {})
        cls.post = staticmethod(post)

        def transport(path, payload):
            return cls.http.post(path, json=payload).get_json()
        cls.builder = OrchestratorClient("axis-video_creator", "video_creator.governor", transport=transport)
        cls.reviewer = OrchestratorClient("axis-validator", "validator.governor", transport=transport)
        cls.silo = OrchestratorClient("axis-video_creator", "video_creator.silos.cgi", transport=transport)
        assert post("/api/bus/register", {"engine": "axis-video_creator", "orchestrator": "video_creator.governor"}, ADMIN).status_code == 200
        assert post("/api/bus/register", {"engine": "axis-validator", "orchestrator": "validator.governor", "qc_reviewer": True}, ADMIN).status_code == 200

    def new_order(self):
        r = self.post("/api/bus/order", {"engine": "axis-video_creator", "to": "video_creator.governor", "spec": {"make": "intro"}}, ADMIN)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["order"]["id"]

    def test_admin_routes_need_the_token(self):
        for path in ("/api/bus/register", "/api/bus/order", "/api/bus/accept"):
            self.assertEqual(self.post(path, {}).status_code, 401, path)
        self.assertEqual(self.http.get("/api/bus/orders").status_code, 401)
        self.assertEqual(self.post("/api/bus/order", {}, {"X-Nexxus-Admin-Token": "wrong"}).status_code, 401)

    def test_an_order_for_a_silo_is_refused_by_the_server(self):
        r = self.post("/api/bus/order", {"engine": "axis-video_creator", "to": "video_creator.silos.cgi", "spec": {}}, ADMIN)
        self.assertEqual(r.status_code, 400)
        self.assertIn("never to a silo", r.get_json()["message"])

    def test_a_silo_cannot_use_the_message_door(self):
        oid = self.new_order()
        reply = self.silo.ack(oid)
        self.assertEqual(reply["status"], "error")
        self.assertIn("not a registered orchestrator", reply["message"])

    def test_a_forged_message_is_refused(self):
        oid = self.new_order()
        env = {"id": "x", "ts": 0, "sender": "video_creator.governor", "to": "nexxus", "kind": "ack", "body": {"order_id": oid}, "sig": "0" * 64}
        r = self.post("/api/bus/message", env)
        self.assertEqual(r.status_code, 400)

    def test_the_whole_honest_path_through_the_server(self):
        oid = self.new_order()
        self.assertEqual(self.builder.ack(oid)["order"]["state"], "ACKED")
        self.assertEqual(self.builder.built(oid, self.artifact)["order"]["state"], "BUILT")
        # accepting before QC is refused
        early = self.post("/api/bus/accept", {"order_id": oid}, ADMIN)
        self.assertEqual(early.status_code, 400)
        # the builder cannot grade its own work (even through its own orchestrator)
        self_grade = self.builder.qc(oid, "pass", [], sha256_file(self.artifact))
        self.assertEqual(self_grade["status"], "error")
        # an independent reviewer passes it
        self.assertEqual(self.reviewer.qc(oid, "pass", [], sha256_file(self.artifact))["order"]["state"], "QC_PASSED")
        done = self.post("/api/bus/accept", {"order_id": oid}, ADMIN)
        self.assertEqual(done.status_code, 200, done.get_json())
        self.assertEqual(done.get_json()["order"]["state"], "ACCEPTED")
        listing = self.http.get("/api/bus/orders", headers=ADMIN).get_json()
        self.assertIn(oid, [o["id"] for o in listing["orders"]])
        self.assertTrue(self.http.get("/api/bus/verify", headers=ADMIN).get_json()["ledger_ok"])

    def test_nexxus_refuses_an_empty_artifact_even_after_a_qc_pass(self):
        empty = os.path.join(TMP, "empty.mp4")
        open(empty, "wb").close()
        oid = self.new_order()
        self.builder.ack(oid)
        self.builder.built(oid, empty)
        self.reviewer.qc(oid, "pass", [], sha256_file(empty))
        r = self.post("/api/bus/accept", {"order_id": oid}, ADMIN)
        self.assertEqual(r.status_code, 400)
        self.assertIn("empty", r.get_json()["message"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
