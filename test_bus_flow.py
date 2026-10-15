"""test_bus_flow.py - a real build-and-QC loop through the real server routes:
NEXXUS orders -> video_creator's orchestrator acknowledges and builds -> curator's orchestrator reviews independently -> NEXXUS accepts.
Run: python test_bus_flow.py"""
import importlib
import json
import os
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="busflow_")
os.environ["NEXXUS_ADMIN_TOKEN"] = "throwaway-admin"
os.environ["NEXXUS_GOVERNANCE_SECRET"] = "throwaway-secret"
os.environ["NEXXUS_BUS_LEDGER"] = os.path.join(TMP, "ledger.jsonl")
os.environ["NEXXUS_NOTIFICATIONS_FILE"] = os.path.join(TMP, "notifs.json")
os.environ["NEXXUS_PERIMETER_DIR"] = os.path.join(os.environ.get("TEMP", "."), "nexxus_test_perimeter_" + str(os.getpid()))
ROOT = os.path.dirname(os.path.abspath(__file__))
SILO = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault")
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import python_server as srv  # noqa: E402
import orchestrator_worker  # noqa: E402
from orchestrator_client import OrchestratorClient  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
SCRIPT = "Software used to be something you rented. NEXXUS is the opposite. It runs on one machine you own."


def load_engine_module(folder):
    """Import <folder>/orchestrator.py without letting two engines' same-named modules (nexxus_link, orchestrator, bootstrap...) collide."""
    path = os.path.join(SILO, folder)
    before_path, before_mods = list(sys.path), set(sys.modules)
    sys.path.insert(0, path)
    try:
        for name in ("orchestrator", "nexxus_link", "bootstrap"):
            sys.modules.pop(name, None)
        return importlib.import_module("orchestrator")
    finally:
        sys.path[:] = before_path
        for name in set(sys.modules) - before_mods:
            if name in ("orchestrator", "nexxus_link", "bootstrap") or name.endswith("_tool") or name.endswith("_config") or name in ("lib", "config"):
                sys.modules.pop(name, None)
        sys.modules.pop("orchestrator", None)


class BuildAndQc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()
        cls.vc = load_engine_module("axis-video_creator")
        cls.cur = load_engine_module("axis-curator")
        transport = lambda path, payload: cls.http.post(path, json=payload).get_json()
        cls.builder = OrchestratorClient("axis-video_creator", "video_creator.governor", transport=transport)
        cls.reviewer = OrchestratorClient("axis-curator", "curator.governor", transport=transport)

    def setUp(self):                                    # every test gets its own fresh bus and ledger, so orders never leak between tests
        os.environ["NEXXUS_BUS_LEDGER"] = os.path.join(tempfile.mkdtemp(prefix="busflow_l_"), "ledger.jsonl")
        srv._bus_holder["bus"] = None
        for engine, orch, qc in (("axis-video_creator", "video_creator.governor", False), ("axis-curator", "curator.governor", True)):
            r = self.http.post("/api/bus/register", json={"engine": engine, "orchestrator": orch, "qc_reviewer": qc}, headers=ADMIN)
            assert r.status_code == 200, r.get_json()

    def order(self, spec):
        r = self.http.post("/api/bus/order", json={"engine": "axis-video_creator", "to": "video_creator.governor", "spec": spec}, headers=ADMIN)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["order"]["id"]

    def state(self, oid):
        orders = self.http.get("/api/bus/orders", headers=ADMIN).get_json()["orders"]
        return next(o["state"] for o in orders if o["id"] == oid)

    def accept(self, oid):
        return self.http.post("/api/bus/accept", json={"order_id": oid}, headers=ADMIN)

    def test_the_whole_loop_ends_in_accepted(self):
        oid = self.order({"kind": "storyboard", "script": SCRIPT, "title": "intro"})
        step = orchestrator_worker.run_once(self.builder, build=self.vc.build)
        self.assertEqual([(d["action"], d["result"]["status"]) for d in step], [("ack", "success")])
        step = orchestrator_worker.run_once(self.builder, build=self.vc.build)
        self.assertEqual([(d["action"], d["result"]["status"]) for d in step], [("build", "success")])
        self.assertEqual(self.state(oid), "BUILT")
        self.assertEqual(self.accept(oid).status_code, 400)                     # not before QC
        self.assertEqual(orchestrator_worker.run_once(self.builder, build=self.vc.build), [])   # the builder has nothing to do and cannot review
        step = orchestrator_worker.run_once(self.reviewer, review=self.cur.review)
        self.assertEqual([(d["action"], d["result"]["status"]) for d in step], [("review", "success")])
        self.assertEqual(self.state(oid), "QC_PASSED")
        self.assertEqual(self.accept(oid).status_code, 200)
        self.assertEqual(self.state(oid), "ACCEPTED")
        board = json.load(open(self.http.get("/api/bus/orders", headers=ADMIN).get_json() and os.path.join(SILO, "axis-video_creator", "builds", oid, "storyboard.json"), encoding="utf-8"))
        self.assertEqual(len(board["scenes"]), 3)
        self.assertTrue(self.http.get("/api/bus/verify", headers=ADMIN).get_json()["ledger_ok"])

    def test_a_bad_build_is_failed_by_the_curator_and_cannot_be_accepted(self):
        oid = self.order({"kind": "storyboard", "script": SCRIPT})
        orchestrator_worker.run_once(self.builder, build=self.vc.build)             # ack

        def sloppy_build(order):                                                    # drops a scene: the builder "forgets" one sentence
            path = self.vc.build(order)
            board = json.load(open(path, encoding="utf-8"))
            board["scenes"].pop()
            json.dump(board, open(path, "w", encoding="utf-8"))
            return path
        orchestrator_worker.run_once(self.builder, build=sloppy_build)
        orchestrator_worker.run_once(self.reviewer, review=self.cur.review)
        self.assertEqual(self.state(oid), "ACKED")                                  # QC failed -> back for rework
        r = self.accept(oid)
        self.assertEqual(r.status_code, 400)
        step = orchestrator_worker.run_once(self.builder, build=self.vc.build)      # the honest rebuild
        self.assertEqual(step[0]["action"], "build")
        orchestrator_worker.run_once(self.reviewer, review=self.cur.review)
        self.assertEqual(self.state(oid), "QC_PASSED")
        self.assertEqual(self.accept(oid).status_code, 200)

    def test_an_order_the_engine_cannot_do_is_never_reported_built(self):
        oid = self.order({"kind": "render_4k_movie"})
        orchestrator_worker.run_once(self.builder, build=self.vc.build)             # ack
        step = orchestrator_worker.run_once(self.builder, build=self.vc.build)
        self.assertEqual(step[0]["result"]["status"], "error")
        self.assertEqual(self.state(oid), "ACKED")

    def test_the_curator_fails_an_empty_file(self):
        oid = self.order({"kind": "storyboard", "script": SCRIPT})
        orchestrator_worker.run_once(self.builder, build=self.vc.build)

        def empty_build(order):
            path = os.path.join(TMP, order["id"] + ".json")
            open(path, "wb").close()
            return path
        orchestrator_worker.run_once(self.builder, build=empty_build)
        orchestrator_worker.run_once(self.reviewer, review=self.cur.review)
        self.assertEqual(self.state(oid), "ACKED")


if __name__ == "__main__":
    unittest.main(verbosity=1)
