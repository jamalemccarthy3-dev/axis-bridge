"""test_governor.py - the governor's ten tools do real work on real state, in a temporary data folder. Run: python test_governor.py"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

DATA = tempfile.mkdtemp(prefix="sandm_gov_")
os.environ["SANDM_DATA"] = DATA
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import sandm_store as store  # noqa: E402


def engine(rel, cls, **cfg):
    class C:
        pass
    c = C()
    for k, v in cfg.items():
        setattr(c, k, v)
    return store.load_engine("src/governor/lib/" + rel, cls, c)


class Governor(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(DATA, ignore_errors=True)
        os.makedirs(DATA)

    def test_audit_trail_is_a_hash_chain_and_notices_edits(self):
        a = engine("audit_trail_logger_tool.py", "AuditTrailLoggerEngine", LOG_FILE_PATH="data/logs/audit_trail.log", AUTO_ROTATE_SIZE_MB=10)
        a.initialize_session_log()
        a.log_event("analyst", "report", "ok")
        a.log_event("strategist", "plan", "ok")
        self.assertEqual(a.verify_chain(), {"ok": True, "records": 3, "first_bad_line": None})
        lines = open(a.path).read().splitlines()
        rec = json.loads(lines[1])
        rec["actor"] = "someone-else"
        lines[1] = json.dumps(rec, sort_keys=True)
        open(a.path, "w").write("\n".join(lines) + "\n")
        self.assertEqual(a.verify_chain()["first_bad_line"], 2)

    def test_audit_trail_rotates_and_restarts_the_chain(self):
        a = engine("audit_trail_logger_tool.py", "AuditTrailLoggerEngine", LOG_FILE_PATH="data/logs/audit_trail.log", AUTO_ROTATE_SIZE_MB=0.0001)
        for i in range(5):
            a.log_event("x", "event %d" % i, "ok")
        self.assertTrue(any(f.startswith("audit_trail.log.") for f in os.listdir(os.path.dirname(a.path))))
        self.assertTrue(a.verify_chain()["ok"])

    def test_kill_switch_halts_the_engine_and_needs_a_name_to_clear(self):
        import main
        k = engine("emergency_kill_switch_tool.py", "KillSwitchEngine", TRIGGER_SIGNAL_PATH="data/state/kill_switch_signal", SHUTDOWN_MODE="HARD_STOP", LOG_TERMINATION_EVENTS=True)
        self.assertFalse(k.is_triggered())
        open(k.signal_path, "w").close() if os.makedirs(os.path.dirname(k.signal_path), exist_ok=True) is None else None
        self.assertTrue(k.is_triggered())
        k.execute_shutdown("test")
        res = main.run_system()
        self.assertTrue(all(str(v).startswith("not started") for v in res.values()), res)
        with self.assertRaises(ValueError):
            k.clear("")
        self.assertTrue(k.clear("jamal"))
        self.assertFalse(k.is_triggered())

    def test_heartbeats_alive_stale_never_seen_and_recovery(self):
        h = engine("heartbeat_monitor_tool.py", "HeartbeatMonitorEngine", CHECK_INTERVAL=30, LOG_STATUS_CHANGES=True)
        self.assertTrue(all(v["status"] == "NEVER_SEEN" for v in h.check_silo_health().values()))
        store.beat("analyst")
        store.write_json("state/heartbeats/strategist.json", {"ts": time.time() - 1000})
        s = h.check_silo_health()
        self.assertEqual((s["analyst"]["status"], s["strategist"]["status"]), ("ALIVE", "STALE"))
        self.assertTrue(h.trigger_recovery("strategist")["recovered"])
        self.assertEqual(h.check_silo_health()["strategist"]["status"], "ALIVE")
        self.assertFalse(h.trigger_recovery("not-a-silo")["recovered"])

    def test_registry_lists_every_utility_from_disk(self):
        r = engine("registry_manager_tool.py", "RegistryManagerEngine", REGISTRY_PATH="data/master_registry.json")
        out = r.sync_registry()
        self.assertEqual((out["silos"], out["missing"], out["unparseable"]), (7, [], []))
        self.assertGreater(out["utilities"], 40)
        self.assertEqual(json.load(open(out["path"]))["silos"]["governor"]["registry_manager.py"]["present"], True)

    def test_balancer_publishes_shares_that_sum_to_one(self):
        class P:
            MAX_THRESHOLD = 2.0
            AGENT_PRIORITIES = {"strategist": 0.4, "technical_agent": 0.3, "analyst": 0.2, "others": 0.1}
        b = store.load_engine("src/governor/lib/resource_balancer_tool.py", "ResourceBalancerEngine", P())
        try:
            import psutil  # noqa: F401
        except ImportError:
            self.assertFalse(b.execute_balancing())
            return
        self.assertTrue(b.execute_balancing())
        shares = store.read_json("state/allocation.json")["shares"]
        self.assertAlmostEqual(sum(shares.values()), 1.0, places=2)
        self.assertEqual(len(shares), 7)
        P.MAX_THRESHOLD = -1
        self.assertFalse(b.execute_balancing())               # over the threshold: no balancing

    def test_gatekeeper_blocks_without_evidence_and_passes_with_it(self):
        reg = engine("registry_manager_tool.py", "RegistryManagerEngine", REGISTRY_PATH="data/master_registry.json")
        aud = engine("audit_trail_logger_tool.py", "AuditTrailLoggerEngine", LOG_FILE_PATH="data/logs/audit_trail.log", AUTO_ROTATE_SIZE_MB=10)
        g = engine("deployment_gatekeeper_tool.py", "DeploymentGatekeeperEngine", REGISTRY_PATH="data/master_registry.json", CHECK_TEST_COVERAGE=80.0,
                   CHECK_SECURITY_VULNERABILITIES=True, REQUIRE_SIGNATURE=True, STAGING_ENV_ONLY=True)
        self.assertFalse(g.verify_deployment_readiness())
        self.assertTrue(store.read_json("state/deployment_block.json"))
        reg.sync_registry()
        aud.log_event("ci", "build", "ok")
        store.write_json("state/test_results.json", {"passed": 90, "failed": 0, "coverage": 91.0})
        store.write_json("state/repo_audit.json", {"findings": [{"severity": "LOW"}]})
        import hashlib
        store.write_json("state/release_signature.json", {"registry_sha256": hashlib.sha256(open(store.resolve("data/master_registry.json"), "rb").read()).hexdigest()})
        store.write_json("state/deploy_request.json", {"target": "staging"})
        self.assertTrue(g.verify_deployment_readiness(), g.last_report)
        store.write_json("state/deploy_request.json", {"target": "production"})
        self.assertFalse(g.verify_deployment_readiness())
        store.write_json("state/deploy_request.json", {"target": "staging"})
        store.write_json("state/test_results.json", {"passed": 90, "failed": 1, "coverage": 91.0})
        self.assertFalse(g.verify_deployment_readiness())

    def test_fusion_syncs_and_notices_hand_edits(self):
        f = engine("fusion_linker_tool.py", "FusionLinkerEngine", ROOT_FUSION_PATH="data/config/root_fusion.json", OVERRIDE_LOCAL_ON_CONFLICT=False, LOG_SYNC_EVENTS=True)
        self.assertFalse(f.verify_link_integrity()["ok"])             # nothing synced yet
        root = f._root()
        root["global"]["mode"] = "decentralized"
        root["silos"]["analyst"] = {"mode": "local-analyst", "extra": 1}
        store.write_json("data/config/root_fusion.json", root)
        self.assertTrue(f.sync_all_configs())
        self.assertTrue(f.verify_link_integrity()["ok"])
        self.assertEqual(store.read_json("state/fusion/analyst.json")["settings"]["mode"], "local-analyst")   # local override wins
        fused = store.read_json("state/fusion/strategist.json")
        fused["settings"]["mode"] = "hacked"
        store.write_json("state/fusion/strategist.json", fused)
        self.assertIn("edited by hand", f.verify_link_integrity()["problems"][0])

    def test_policy_baseline_then_drift(self):
        p = engine("policy_validator_tool.py", "PolicyValidatorEngine", POLICY_FILE="data/config/sovereign_shift_policy.json")
        self.assertTrue(p.verify_system_policies())
        self.assertTrue(p.baseline_created)
        pol = store.read_json("data/config/sovereign_shift_policy.json")
        pol["mode"] = "centralized"
        del pol["silos"]["analyst"]
        store.write_json("data/config/sovereign_shift_policy.json", pol)
        p2 = engine("policy_validator_tool.py", "PolicyValidatorEngine", POLICY_FILE="data/config/sovereign_shift_policy.json")
        self.assertFalse(p2.verify_system_policies())
        self.assertEqual({d[0] for d in p2.drift}, {"mode", "silo:analyst"})
        self.assertEqual(len(store.read_jsonl("drift.jsonl")), 2)

    def test_protocol_enforcer_reads_the_bus_and_escalates(self):
        e = engine("protocol_enforcer_tool.py", "ProtocolEnforcerEngine")
        log = store.engine_path("logs", "event_bus.log")
        saved = open(log).read() if os.path.exists(log) else None
        try:
            open(log, "w").write(json.dumps({"event": "a", "data": 1}) + "\n" + "garbage\n" + json.dumps({"event": "", "data": 1}) + "\n" + json.dumps({"event": "b"}) + "\n")
            self.assertFalse(e.validate_active_protocols())
            self.assertEqual([n for n, _ in e.violations], [2, 3, 4])
            open(log, "w").write(json.dumps({"event": "a", "data": 1}) + "\n")
            self.assertTrue(e.validate_active_protocols())
        finally:
            if saved is None:
                os.remove(log)
            else:
                open(log, "w").write(saved)
        self.assertEqual(e.enforce_security("low"), ["audit"])
        self.assertEqual(e.enforce_security("HIGH"), ["audit", "violation_record", "deployment_blocked"])
        self.assertIsNone(store.halted())
        self.assertEqual(e.enforce_security("CRITICAL")[-1], "kill_switch")
        self.assertIsNotNone(store.halted())
        with self.assertRaises(ValueError):
            e.enforce_security("meh")

    def test_dispatcher_validates_orders_by_priority_and_routes(self):
        d = engine("instruction_dispacter_tool.py", "InstructionDispatcherEngine", QUEUE_LIMIT=3, PRIORITY_LEVELS=["CRITICAL", "HIGH", "NORMAL", "LOW"])
        self.assertFalse(d.process_queue())                           # empty
        d.submit({"target": "analyst", "task": "low one", "priority": "LOW"})
        d.submit({"target": "analyst", "task": "critical one", "priority": "CRITICAL"})
        with self.assertRaises(ValueError):
            d.submit({"target": "nobody", "task": "x"})
        self.assertTrue(d.process_queue())
        tasks = [t["task"] for t in store.read_jsonl("queue/tasks_analyst.jsonl")]
        self.assertEqual(tasks, ["critical one", "low one"])
        self.assertFalse(d.process_queue())                           # nothing pending now
        for i in range(3):
            d.submit({"target": "strategist", "task": "t%d" % i})
        with self.assertRaises(ValueError):
            d.submit({"target": "strategist", "task": "one too many"})

    def test_tool_request_runs_only_governor_tools_audits_them_and_obeys_the_kill_switch(self):
        sys.path.insert(0, os.path.join(ROOT, "src", "governor"))
        import importlib
        tr = importlib.import_module("tool_request")
        rec = tr.run_tool("audit_trail_logger", "log_event", "analyst", "hello", "ok")
        self.assertEqual(rec["actor"], "analyst")
        self.assertTrue(tr.run_tool("registry_manager", "sync_registry")["silos"] == 7)
        self.assertTrue(any(r["actor"] == "tool_request" and r["action"] == "registry_manager.sync_registry" for r in store.read_jsonl("data/logs/audit_trail.log")))
        for bad in (("nope", "x"), ("registry_manager", "_private"), ("registry_manager", "does_not_exist")):
            with self.assertRaises(ValueError):
                tr.run_tool(*bad)
        tr.run_tool("emergency_kill_switch", "execute_shutdown", "test")
        with self.assertRaises(PermissionError):
            tr.run_tool("registry_manager", "sync_registry")
        self.assertTrue(tr.run_tool("emergency_kill_switch", "clear", "jamal"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
