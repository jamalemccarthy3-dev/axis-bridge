"""test_sentinel.py - axis-integrity as a real auditor: it patrols, notices engines that appear or vanish, notices a tampered ledger, refuses fake credentials and
never claims to have frozen anything. Uses a temporary silo and temporary logs. Run: python test_sentinel.py"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

WORLD = tempfile.mkdtemp(prefix="sentinel_")
SILO = os.path.join(WORLD, "silo")
LOGS = os.path.join(WORLD, "logs")
os.environ["AXIS_INTEGRITY_SILO_ROOT"] = SILO
os.environ["AXIS_INTEGRITY_LOGS"] = LOGS
os.environ["NEXXUS_GOVERNANCE_SECRET"] = "unit-test-secret"
os.environ.setdefault("NEXXUS_MESH_URL", "http://127.0.0.1:9")

ROOT = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(ROOT, "auditor_interface", "config"), os.path.join(ROOT, "auditor_interface", "lib"), os.path.join(ROOT, "auditor_interface")):
    sys.path.insert(0, p)

import alert_registry_tool  # noqa: E402
import auditor  # noqa: E402
import auth_protocol  # noqa: E402
import auth_protocol_tool  # noqa: E402
import freeze_all  # noqa: E402
import governance  # noqa: E402
import ledger  # noqa: E402
import silo_inventory_map  # noqa: E402


def engine(name, pulse_age=0):
    d = os.path.join(SILO, name)
    os.makedirs(d, exist_ok=True)
    pulse = os.path.join(d, "system_pulse.log")
    with open(pulse, "w") as f:
        f.write("pulse\n")
    t = time.time() - pulse_age
    os.utime(pulse, (t, t))


class Sentinel(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(SILO, ignore_errors=True)
        shutil.rmtree(LOGS, ignore_errors=True)
        os.makedirs(SILO)
        engine("axis-a")
        engine("axis-b")
        auth_protocol_tool._failures.clear()
        self.reports = []
        self.rep = lambda kind, detail: self.reports.append((kind, detail))

    def test_a_healthy_silo_has_no_findings(self):
        r = auditor.run_sentinel_cycle(self.rep)
        self.assertEqual((r["patrolled"], r["alive"], r["findings"], r["ledger_ok"]), (2, 2, [], True))
        self.assertEqual(self.reports, [])

    def test_an_engine_that_appears_is_a_critical_finding_and_is_reported(self):
        auditor.run_sentinel_cycle(self.rep)                      # writes the baseline
        engine("axis-intruder")
        r = auditor.run_sentinel_cycle(self.rep)
        crit = [f for f in r["findings"] if f["severity"] == "CRITICAL"]
        self.assertEqual([f["silo"] for f in crit], ["axis-intruder"])
        self.assertEqual(r["inventory"]["new"], ["axis-intruder"])
        self.assertEqual(self.reports[0][0], "SENTINEL_CRITICAL")
        self.assertEqual(r["reported_to_nexxus"], 1)
        with open(os.path.join(LOGS, "system.ledger.jsonl"), encoding="utf-8") as f:
            texts = [json.loads(l)["message"] for l in f]
        self.assertTrue(any("FREEZE_RECOMMENDED" in t for t in texts))
        self.assertTrue(any(a["severity"] == "CRITICAL" for a in alert_registry_tool.list_alerts()))

    def test_an_engine_that_vanishes_is_a_critical_finding(self):
        auditor.run_sentinel_cycle(self.rep)
        shutil.rmtree(os.path.join(SILO, "axis-b"))
        r = auditor.run_sentinel_cycle(self.rep)
        self.assertEqual(r["inventory"]["missing"], ["axis-b"])
        self.assertTrue(any(f["severity"] == "CRITICAL" and f["silo"] == "axis-b" for f in r["findings"]))

    def test_an_engine_with_a_stale_pulse_is_a_warning(self):
        engine("axis-a", pulse_age=2 * 24 * 3600)
        r = auditor.run_sentinel_cycle(self.rep)
        self.assertEqual([(f["severity"], f["silo"]) for f in r["findings"]], [("WARNING", "axis-a")])
        self.assertEqual(r["alive"], 1)

    def test_a_tampered_ledger_is_noticed(self):
        auditor.run_sentinel_cycle(self.rep)
        engine("axis-x")
        auditor.run_sentinel_cycle(self.rep)                      # something is in the ledger now
        path = os.path.join(LOGS, "system.ledger.jsonl")
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        e = json.loads(lines[0])
        e["message"] = "EVENT: nothing happened"
        lines[0] = json.dumps(e, sort_keys=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        r = auditor.run_sentinel_cycle(self.rep)
        self.assertFalse(r["ledger_ok"])
        self.assertTrue(any("tampered" in f["message"] for f in r["findings"]))

    def test_governance_recommends_a_freeze_but_never_claims_to_have_done_it(self):
        out = governance.evaluate_compliance({"severity": "CRITICAL", "silo_id": "axis-a", "message": "bad"})
        self.assertFalse(out["freeze"]["frozen"])
        self.assertTrue(out["freeze"]["recommended"])
        self.assertIsNone(governance.evaluate_compliance({"severity": "INFO", "silo_id": "axis-a", "message": "fine"})["freeze"])
        r = freeze_all.trigger_emergency_lockdown()
        self.assertEqual((r["executed"], r["requested"]), (False, True))

    def test_the_old_hard_coded_token_is_rejected_and_real_tokens_work(self):
        self.assertFalse(auth_protocol.authorize_request("VALID_SECURE_TOKEN", "omni"))
        good = auth_protocol_tool.issue_token("omni")
        self.assertTrue(auth_protocol.authorize_request(good, "omni"))
        self.assertFalse(auth_protocol.authorize_request(good, "someone-else"))          # a token belongs to one persona

    def test_three_wrong_tokens_lock_the_persona(self):
        good = auth_protocol_tool.issue_token("omni")
        for _ in range(3):
            self.assertFalse(auth_protocol.authorize_request("wrong", "omni"))
        self.assertFalse(auth_protocol.authorize_request(good, "omni"))                   # locked, even with the right token
        self.assertTrue(auth_protocol_tool.locked("omni"))

    def test_without_a_secret_nothing_is_authorised(self):
        saved = os.environ.pop("NEXXUS_GOVERNANCE_SECRET")
        try:
            self.assertFalse(auth_protocol_tool.verify_token("anything", "omni"))
            with self.assertRaises(RuntimeError):
                auth_protocol_tool.issue_token("omni")
        finally:
            os.environ["NEXXUS_GOVERNANCE_SECRET"] = saved

    def test_alerts_are_kept_and_capped(self):
        a = alert_registry_tool.store_alert({"msg": "x", "severity": "loud"})
        self.assertEqual((a["severity"], a["severity_given"]), ("INFO", "LOUD"))
        for i in range(60):
            alert_registry_tool.store_alert({"msg": "m%d" % i, "severity": "WARNING"})
        self.assertEqual(len(alert_registry_tool.list_alerts()), 50)
        self.assertTrue(alert_registry_tool.close_alert(alert_registry_tool.list_alerts()[-1]["id"]))
        self.assertEqual(len(alert_registry_tool.list_alerts()), 49)

    def test_only_baseline_engines_are_authorised(self):
        auditor.run_sentinel_cycle(self.rep)
        self.assertTrue(silo_inventory_map.verify_district("axis-a"))
        self.assertFalse(silo_inventory_map.verify_district("axis-unknown"))
        self.assertTrue(ledger.verify()[0])


if __name__ == "__main__":
    unittest.main(verbosity=1)
