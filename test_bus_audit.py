"""test_bus_audit.py - axis-core reports to axis-integrity through NEXXUS, and the witness catches a core that lies.
Core -> the real server routes (Flask test client) -> NEXXUS's ledger -> the audit feed -> axis-integrity's Auditor and witness.
Run: python test_bus_audit.py"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="busaud_")
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
from orchestrator_client import OrchestratorClient  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
ALLOWED = {"axis_switchboard.exe", "sender.exe"}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeNative:
    """A pure-Python stand-in for the compiled SDK, with the same rule, so the audit logic can be tested without a compiler."""

    def __init__(self):
        self.armed = False
        self.calls = []

    def _ghosts(self, folder):
        return [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)) and f not in ALLOWED]

    def purge_report(self, folder):
        self.calls.append("report")
        return len(self._ghosts(folder))

    def purge_confirmed(self, folder, confirmed):
        self.calls.append("confirmed")
        if confirmed is not True:
            return -1
        g = self._ghosts(folder)
        for f in g:
            os.remove(os.path.join(folder, f))
        return len(g)

    def initialize_security(self):
        self.armed = True

    def security_is_active(self):
        return self.armed


def folder_with(*names):
    d = tempfile.mkdtemp(prefix="core_")
    for n in names:
        open(os.path.join(d, n), "w").close()
    return d


class CoreToIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()
        cls.core_mod = load(os.path.join(SILO, "axis-core", "orchestrator.py"), "t_core_orch")
        cls.integ_mod = load(os.path.join(SILO, "axis-integrity", "orchestrator.py"), "t_integ_orch")
        cls.Auditor = load(os.path.join(SILO, "axis-integrity", "lib", "auditor.py"), "t_auditor").Auditor
        cls.Witness = load(os.path.join(SILO, "axis-integrity", "witness.py"), "t_witness").Witness
        cls.transport = staticmethod(lambda path, payload: cls.http.post(path, json=payload).get_json())

    def setUp(self):
        os.environ["NEXXUS_BUS_LEDGER"] = os.path.join(tempfile.mkdtemp(prefix="busaud_l_"), "ledger.jsonl")
        srv._bus_holder["bus"] = None
        reg = lambda e, o, **k: self.http.post("/api/bus/register", json=dict(engine=e, orchestrator=o, **k), headers=ADMIN)
        assert reg("axis-core", "core.governor").status_code == 200
        assert reg("axis-integrity", "integrity.governor", auditor=True).status_code == 200
        self.core_link = OrchestratorClient("axis-core", "core.governor", transport=self.transport)
        self.integ_link = OrchestratorClient("axis-integrity", "integrity.governor", transport=self.transport)
        self.auditor = self.Auditor(os.path.join(tempfile.mkdtemp(prefix="aud_"), "a.jsonl"))
        self.witness = self.Witness(self.auditor)
        self.native = FakeNative()
        self.core = self.core_mod.CoreOrchestrator(self.core_link, self.native)

    def ingest(self):
        return self.integ_mod.ingest_once(self.integ_link, auditor=self.auditor, witness=self.witness)

    def kinds(self):
        return [e["kind"] for e in self.auditor.events()]

    # ---- the honest path
    def test_an_honest_purge_is_reported_recorded_and_checked(self):
        d = folder_with("axis_switchboard.exe", "ghost.txt", "ghost2.dat")
        self.assertEqual(self.core.purge(d, confirmed=True), 2)
        self.assertEqual(self.ingest(), 2)
        self.assertEqual(self.kinds(), ["axis-core:PURGE_REQUESTED", "axis-core:PURGE_DONE"])       # the request came first
        self.assertEqual(self.ingest(), 0)                                                          # confirmed: not offered again
        self.assertTrue(self.auditor.verify()[0])

    def test_arming_the_lock_is_reported_first(self):
        self.assertTrue(self.core.arm_security())
        self.ingest()
        self.assertEqual(self.kinds(), ["axis-core:SECURITY_ARMING", "axis-core:SECURITY_ARMED"])

    def test_a_report_only_purge_removes_nothing_and_is_reported(self):
        d = folder_with("ghost.txt")
        self.assertEqual(self.core.purge(d, confirmed=False), 1)
        self.assertTrue(os.path.isfile(os.path.join(d, "ghost.txt")))
        self.ingest()
        self.assertEqual(self.kinds(), ["axis-core:PURGE_REPORT_ONLY"])

    # ---- the guard: no record, no deletion
    def test_if_the_report_cannot_be_made_nothing_is_deleted(self):
        d = folder_with("ghost.txt")
        offline = OrchestratorClient("axis-core", "core.governor", transport=lambda p, b: {"status": "error", "message": "NEXXUS is not reachable"})
        core = self.core_mod.CoreOrchestrator(offline, self.native)
        with self.assertRaises(self.core_mod.CoreAuditUnavailable):
            core.purge(d, confirmed=True)
        self.assertTrue(os.path.isfile(os.path.join(d, "ghost.txt")))
        self.assertNotIn("confirmed", self.native.calls)
        raising = OrchestratorClient("axis-core", "core.governor", transport=lambda p, b: (_ for _ in ()).throw(ConnectionError("down")))
        with self.assertRaises(self.core_mod.CoreAuditUnavailable):
            self.core_mod.CoreOrchestrator(raising, self.native).purge(d, confirmed=True)

    # ---- the witness catches a core that lies
    def test_a_lying_core_is_caught(self):
        d = folder_with("ghost.txt", "ghost2.dat")
        self.core_link.audit("PURGE_DONE", d + ": 2 file(s)")           # claims a purge nobody asked for, and the files are still there
        self.ingest()
        findings = [e for e in self.auditor.events() if e["kind"].startswith("FINDING:")]
        self.assertEqual({f["kind"] for f in findings}, {"FINDING:CRITICAL"})
        self.assertEqual(len(findings), 2)                               # no request, and the ghosts are still there
        self.assertTrue(self.auditor.verify()[0])

    # ---- who may use the feed
    def test_only_an_auditor_can_confirm_the_feed(self):
        self.core_link.audit("X", "y")
        r = self.core_link.audit_ack(1)
        self.assertEqual(r["status"], "error")
        self.assertIn("not an auditor", r["message"])

    def test_a_silo_cannot_report(self):
        silo = OrchestratorClient("axis-core", "core.silos.pipe", transport=self.transport)
        self.assertEqual(silo.audit("PURGE_DONE", "x")["status"], "error")

    def test_a_non_auditor_does_not_receive_the_feed(self):
        self.core_link.audit("SECURITY_ARMING", "x")
        self.assertEqual(self.core_link.poll()["orders"], [])
        self.assertEqual(len(self.integ_link.poll()["orders"]), 1)

    def test_events_are_offered_again_until_they_are_confirmed(self):
        self.core_link.audit("SECURITY_ARMING", "x")
        a = self.integ_link.poll()["orders"][0]
        b = self.integ_link.poll()["orders"][0]
        self.assertEqual(a["upto"], b["upto"])                           # nothing was confirmed, so nothing was dropped
        self.assertEqual(self.integ_link.audit_ack(a["upto"])["status"], "success")
        self.assertEqual(self.integ_link.poll()["orders"], [])

    def test_bad_audit_input_is_refused(self):
        self.assertEqual(self.core_link.audit("", "x")["status"], "error")
        self.assertEqual(self.core_link.audit("K", "x" * 2001)["status"], "error")
        self.assertEqual(self.integ_link.audit_ack(999)["status"], "error")

    def test_the_reports_are_in_nexxus_ledger_and_survive_a_restart(self):
        self.core_link.audit("SECURITY_ARMING", "x")
        self.assertTrue(self.http.get("/api/bus/verify", headers=ADMIN).get_json()["ledger_ok"])
        srv._bus_holder["bus"] = None                                    # a restart: the bus is rebuilt from its ledger
        self.assertEqual(len(self.integ_link.poll()["orders"][0]["events"]), 1)


class RealSdk(unittest.TestCase):
    """The same flow with the REAL compiled SDK (axis_core.dll). Skipped without a C compiler or off Windows."""

    @classmethod
    def setUpClass(cls):
        cls.native_mod = load(os.path.join(SILO, "axis-core", "core_native.py"), "t_core_native")
        cls.native = cls.native_mod.load()

    def test_a_real_purge_through_the_dll_is_reported_and_checked(self):
        if self.native is None:
            self.skipTest("no C compiler or not Windows")
        http = srv.app.test_client()
        os.environ["NEXXUS_BUS_LEDGER"] = os.path.join(tempfile.mkdtemp(prefix="busaud_r_"), "ledger.jsonl")
        srv._bus_holder["bus"] = None
        http.post("/api/bus/register", json={"engine": "axis-core", "orchestrator": "core.governor"}, headers=ADMIN)
        http.post("/api/bus/register", json={"engine": "axis-integrity", "orchestrator": "integrity.governor", "auditor": True}, headers=ADMIN)
        tr = lambda path, payload: http.post(path, json=payload).get_json()
        core = load(os.path.join(SILO, "axis-core", "orchestrator.py"), "t_core_orch2").CoreOrchestrator(OrchestratorClient("axis-core", "core.governor", transport=tr), self.native)
        d = folder_with("axis_switchboard.exe", "sender.exe", "ghost.txt")
        self.assertEqual(core.purge(d, confirmed=True), 1)
        self.assertFalse(os.path.isfile(os.path.join(d, "ghost.txt")))
        self.assertTrue(os.path.isfile(os.path.join(d, "sender.exe")))
        integ = OrchestratorClient("axis-integrity", "integrity.governor", transport=tr)
        Auditor = load(os.path.join(SILO, "axis-integrity", "lib", "auditor.py"), "t_auditor2").Auditor
        Witness = load(os.path.join(SILO, "axis-integrity", "witness.py"), "t_witness2").Witness
        aud = Auditor(os.path.join(tempfile.mkdtemp(prefix="aud_"), "a.jsonl"))
        load(os.path.join(SILO, "axis-integrity", "orchestrator.py"), "t_integ_orch2").ingest_once(integ, auditor=aud, witness=Witness(aud))
        self.assertEqual([e["kind"] for e in aud.events()], ["axis-core:PURGE_REQUESTED", "axis-core:PURGE_DONE"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
