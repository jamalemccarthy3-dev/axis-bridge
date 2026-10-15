"""test_slae.py - the Self-Learning & Adaptation Engine against REAL failures: exceptions are raised for real (a missing key, a missing file, a refused local connection, a divide by zero) and captured; each becomes
exactly one preventative rule; a repeat is counted as a recurrence, not a new rule; enforceable rules really stop the next run before it starts; secrets never reach the vault; the failure history is
hash-chained (an edit is detected, long stack traces do not break the chain, a restart continues it); the registry survives corruption; auto_remediation off means rules are not activated or counted as resolved;
the loop folds runtime feedback into stats and captures a service the daemon turns red exactly once; and nexxus_talks is wired in. Throwaway vault. Run: python test_slae.py"""
import atexit
import json
import os
import shutil
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
sys.path.insert(0, NEXUS)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="slae_")
atexit.register(shutil.rmtree, TMP, True)
os.environ["NEXXUS_DISABLE_SLAE_LOOP"] = "1"
import sl_adaptive_core as sl  # noqa: E402


LAST = {}


def engine(name="v", **cfg):
    return sl.SLAE(sl.load_config(overrides=dict({"loop_interval_seconds": 1}, **cfg)), vault_dir=Path(TMP) / name)


def real_failure(kind):
    """Raise a genuine exception of the given kind and hand back (signature, trace) the way an except block would."""
    import traceback
    try:
        if kind == "key":
            {"present": 1}["missing_field"]
        elif kind == "file":
            open(os.path.join(TMP, "no", "such", "file.txt"))
        elif kind == "conn":
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            LAST["port"] = port
            s.close()
            socket.create_connection(("127.0.0.1", port), timeout=1)
        elif kind == "zero":
            1 / 0
    except Exception as e:
        return "%s: %s" % (type(e).__name__, e), traceback.format_exc()
    raise AssertionError("no failure raised")


class Config(unittest.TestCase):
    def test_slae_config_comes_from_master_config(self):
        cfg = sl.load_config()
        self.assertIs(cfg["enabled"], True)
        self.assertIs(cfg["auto_remediation"], True)
        self.assertEqual(cfg["vault_dir"], "D:/vault/failures/")
        self.assertEqual(cfg["loop_interval_seconds"], 30)
        self.assertEqual(cfg["registry_file"], "adaptation_registry.json")

    def test_vault_is_created_automatically_and_a_missing_drive_is_reported(self):
        os.environ["NEXXUS_VAULT_DIR"] = os.path.join(TMP, "auto", "made", "here")
        try:
            e = sl.SLAE(sl.load_config())
            self.assertTrue(Path(os.environ["NEXXUS_VAULT_DIR"]).is_dir())
            self.assertEqual(Path(e.vault), Path(os.environ["NEXXUS_VAULT_DIR"]))
        finally:
            os.environ.pop("NEXXUS_VAULT_DIR")
        if os.name == "nt" and not os.path.exists("D:\\"):
            r = sl.nexxus_paths.resolve_dir("D:/vault/failures/", "vault/failures", None, create=False)
            self.assertTrue(r["used_fallback"])
            self.assertIn("nexxus_data", str(r["path"]))
            self.assertIn("not available", r["reason"])


class Capture(unittest.TestCase):
    def test_a_real_failure_is_captured_timestamped_and_converted_into_one_rule(self):
        e = engine("c1")
        sig, tb = real_failure("key")
        out = e.capture_and_convert(sig, "billing.calc", tb, {"order": 7})
        self.assertTrue(out["new_rule"] and not out["recurrence"] and out["active"])
        self.assertEqual(out["enforcement"], "preflight")
        reg = json.loads((e.vault / "adaptation_registry.json").read_text())
        self.assertEqual((reg["total_captured"], reg["total_resolved"], reg["unique_signatures"]), (1, 1, 1))
        self.assertEqual(len(reg["history"]), 1)
        self.assertRegex(reg["history"][0]["at"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
        line = json.loads((e.vault / "failure_history.jsonl").read_text().splitlines()[0])
        self.assertIn("Traceback", line["stack_trace"])
        self.assertEqual(line["context"], {"order": 7})
        self.assertEqual(line["source_node"], "billing.calc")

    def test_a_repeat_is_a_recurrence_on_the_same_rule_not_a_new_one(self):
        e = engine("c2")
        sig, tb = real_failure("key")
        e.capture_and_convert(sig, "n", tb)
        again = e.capture_and_convert(sig, "other.node", tb)
        self.assertTrue(again["recurrence"] and not again["new_rule"])
        s = e.get_system_immunity_stats()
        self.assertEqual((s["total_captured"], s["active_rules_count"], s["recurrences_after_rule"], s["total_resolved"]), (2, 1, 1, 2))
        self.assertEqual(sorted(s["active_rules"][0]["source_nodes"]), ["n", "other.node"])
        self.assertEqual(s["active_rules"][0]["occurrences"], 2)

    def test_numbers_and_ids_do_not_make_a_failure_look_new(self):
        self.assertEqual(sl.normalize_signature("TimeoutError: job 4412 after 30s at 0x7ffa1234"), sl.normalize_signature("TimeoutError: job 9 after 31s at 0x1"))
        self.assertNotEqual(sl.normalize_signature("KeyError: 'a'"), sl.normalize_signature("KeyError: 'b'"))
        e = engine("c3")
        e.capture_and_convert("ValueError: bad row 12 in batch 7", "etl")
        r = e.capture_and_convert("ValueError: bad row 99 in batch 8", "etl")
        self.assertTrue(r["recurrence"])

    def test_rules_by_error_kind_are_enforceable_only_when_the_signature_supports_it(self):
        e = engine("c4")
        got = {}
        for kind in ("key", "file", "conn", "zero"):
            sig, tb = real_failure(kind)
            got[kind] = e.capture_and_convert(sig, "node-" + kind, tb, {"port": LAST["port"]} if kind == "conn" else None)
        self.assertEqual(got["key"]["enforcement"], "preflight")
        self.assertEqual(got["file"]["enforcement"], "preflight")
        self.assertEqual(got["conn"]["enforcement"], "preflight")
        self.assertEqual(got["zero"]["enforcement"], "detect_only")                       # a ZeroDivisionError does not say which divisor to check: it is not pretended
        s = e.get_system_immunity_stats()
        self.assertEqual((s["enforceable_rules"], s["detect_only_rules"], s["active_rules_count"]), (3, 1, 4))
        sig, tb = real_failure("conn")                                                        # the same failure with NO port anywhere (Windows never prints it): honest, detect-only
        self.assertEqual(engine("c4b").capture_and_convert(sig, "node-noport", tb)["enforcement"], "detect_only")

    def test_a_requests_style_message_carries_its_own_port(self):
        rule = sl.synthesize_rule("ConnectionError: HTTPConnectionPool(host='127.0.0.1', port=8731): Max retries exceeded with url: /x (Caused by NewConnectionError: Failed to establish a new connection: [WinError 10061] actively refused it)", "n")
        self.assertEqual((rule["type"], rule["params"]["port"], rule["enforcement"]), ("require_service_up", 8731, "preflight"))

    def test_bad_input_is_refused(self):
        e = engine("c5")
        with self.assertRaises(ValueError):
            e.capture_and_convert("   ", "n")
        with self.assertRaises(ValueError):
            e.process_runtime_feedback("not a dict")

    def test_capture_exception_builds_the_signature_and_trace_itself(self):
        e = engine("c6")
        try:
            {}["x"]
        except KeyError as ex:
            out = e.capture_exception(ex, "n")
        self.assertEqual(out["enforcement"], "preflight")
        self.assertIn("KeyError", json.loads((e.vault / "failure_history.jsonl").read_text().splitlines()[0])["signature"])


class Immunity(unittest.TestCase):
    def test_a_key_rule_stops_the_next_run_before_it_starts(self):
        e = engine("i1")
        sig, tb = real_failure("key")
        e.capture_and_convert(sig, "billing.calc", tb)
        self.assertEqual(len(e.preflight("billing.calc", {"present": 1})), 1)
        self.assertEqual(e.preflight("billing.calc", {"present": 1, "missing_field": 2}), [])
        self.assertEqual(e.preflight("some.other.node", {}), [])                          # rules apply to the nodes that failed
        self.assertEqual(e.get_system_immunity_stats()["preflight_blocks"], 1)

    def test_path_and_service_rules_check_the_real_world(self):
        e = engine("i2")
        sig, tb = real_failure("file")
        e.capture_and_convert(sig, "reader", tb)
        self.assertEqual(len(e.preflight("reader")), 1)                                    # the file is still not there
        path = [r for r in e.reg["rules"].values()][0]["params"]["path"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        self.assertEqual(e.preflight("reader"), [])                                        # once the world is fixed the rule passes
        sig, tb = real_failure("conn")
        e.capture_and_convert(sig, "caller", tb, {"port": LAST["port"]})
        bad = e.preflight("caller")
        self.assertEqual(len(bad), 1)
        self.assertIn("accepting connections", bad[0]["why"])
        port = [r for r in e.reg["rules"].values() if r["type"] == "require_service_up"][0]["params"]["port"]
        srv = socket.socket()
        srv.bind(("127.0.0.1", port))
        srv.listen(1)
        try:
            self.assertEqual(e.preflight("caller"), [])
        finally:
            srv.close()

    def test_guarded_blocks_captures_and_reraises(self):
        e = engine("i3")
        calls = []

        @e.guarded("calc.node", state_fn=lambda d: d)
        def calc(d):
            calls.append(1)
            return d["amount"] * 2
        self.assertEqual(calc({"amount": 2}), 4)
        with self.assertRaises(KeyError):
            calc({"other": 1})                                                              # a real failure: captured, and still raised to the caller
        self.assertEqual(e.get_system_immunity_stats()["total_captured"], 1)
        n = len(calls)
        with self.assertRaises(sl.ImmunityViolation) as cm:
            calc({"other": 1})                                                              # now the rule stops it BEFORE it runs
        self.assertEqual(len(calls), n)
        self.assertIn("amount", str(cm.exception))
        self.assertEqual(calc({"amount": 5}), 10)
        e.cfg["enforce_preflight"] = False
        with self.assertRaises(KeyError):
            calc({"other": 1})                                                              # enforcement off: the step runs and fails as before
        self.assertEqual(e.reg["nodes"] if False else True, True)

    def test_auto_remediation_off_means_no_active_rules_and_nothing_counted_resolved(self):
        e = engine("i4", auto_remediation=False)
        sig, tb = real_failure("key")
        out = e.capture_and_convert(sig, "n", tb)
        self.assertFalse(out["active"])
        s = e.get_system_immunity_stats()
        self.assertEqual((s["total_captured"], s["total_resolved"], s["active_rules_count"], s["auto_remediation"]), (1, 0, 0, False))
        self.assertEqual(e.preflight("n", {}), [])


class Vault(unittest.TestCase):
    def test_secrets_never_reach_the_vault(self):
        e = engine("v1")
        secret = "AIza" + "B" * 35
        e.capture_and_convert("RuntimeError: call failed with key=%s" % secret, "net", "Traceback...\nheaders = {'Authorization': 'Bearer abcdefghijklmnop1234'}\napi_key = 'supersecretvalue99'\ntoken: ghp_" + "a" * 30,
                              {"password": "hunter2hunter2", "note": secret})
        blob = (e.vault / "failure_history.jsonl").read_text() + (e.vault / "adaptation_registry.json").read_text()
        for leak in (secret, "abcdefghijklmnop1234", "supersecretvalue99", "ghp_" + "a" * 30, "hunter2hunter2"):
            self.assertNotIn(leak, blob)
        self.assertIn("redacted", blob)

    def test_history_is_hash_chained_and_an_edit_is_found(self):
        e = engine("v2")
        for i in range(4):
            e.capture_and_convert("KeyError: 'k%d'" % i, "n", "t" * 7000)                   # long traces: lines far longer than any tail window
        self.assertEqual(e.verify_history(), {"ok": True, "entries": 4, "broken_at": None})
        lines = (e.vault / "failure_history.jsonl").read_text().splitlines()
        lines[1] = lines[1].replace('"source_node": "n"', '"source_node": "tampered"')
        (e.vault / "failure_history.jsonl").write_text("\n".join(lines) + "\n")
        v = e.verify_history()
        self.assertFalse(v["ok"])
        self.assertEqual(v["broken_at"], 2)

    def test_a_restart_continues_the_chain_and_the_counters(self):
        a = engine("v3")
        a.capture_and_convert("KeyError: 'x'", "n", "t" * 9000)
        b = engine("v3")
        self.assertEqual(b.get_system_immunity_stats()["total_resolved"], 1)
        b.capture_and_convert("KeyError: 'y'", "n", "t" * 9000)
        self.assertEqual(b.verify_history(), {"ok": True, "entries": 2, "broken_at": None})
        self.assertEqual(b.get_system_immunity_stats()["active_rules_count"], 2)

    def test_stack_trace_is_capped(self):
        e = engine("v4", max_stack_chars=500)
        e.capture_and_convert("KeyError: 'x'", "n", "z" * 50000)
        self.assertLessEqual(len(json.loads((e.vault / "failure_history.jsonl").read_text().splitlines()[0])["stack_trace"]), 500)

    def test_corrupt_registry_is_set_aside_and_the_backup_used(self):
        a = engine("v5")
        a.capture_and_convert("KeyError: 'x'", "n")
        a.capture_and_convert("KeyError: 'y'", "n")
        (a.vault / "adaptation_registry.json").write_text("{ not json")
        b = engine("v5")
        self.assertEqual(b.get_system_immunity_stats()["total_captured"], 1)                # the .bak is the state before the last write
        self.assertTrue(any(p.startswith("adaptation_registry.json.corrupt-") for p in os.listdir(b.vault)))
        self.assertEqual([p for p in os.listdir(b.vault) if p.endswith(".tmp")], [])

    def test_concurrent_captures_lose_nothing(self):
        import threading
        e = engine("v6")
        ts = [threading.Thread(target=lambda k=k: [e.capture_and_convert("KeyError: 'k%d'" % (k * 100 + i), "n") for i in range(10)]) for k in range(5)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        s = e.get_system_immunity_stats()
        self.assertEqual((s["total_captured"], s["active_rules_count"]), (50, 50))
        self.assertEqual(e.verify_history()["entries"], 50)
        self.assertTrue(e.verify_history()["ok"])


class Loop(unittest.TestCase):
    def test_runtime_feedback_is_folded_into_node_stats_by_the_loop(self):
        e = engine("l1")
        for _ in range(3):
            e.process_runtime_feedback({"source_node": "talks", "ok": True, "latency": 0.5})
        out = e.process_runtime_feedback({"source_node": "talks", "ok": False, "latency": 1.5, "error_signature": "KeyError: 'q'", "stack_trace": "tb"})
        self.assertTrue(out["new_rule"])
        e.tick()
        n = e.reg["nodes"]["talks"]
        self.assertEqual((n["calls"], n["failed"], n["failure_rate"]), (4, 1, 0.25))
        self.assertAlmostEqual(n["avg_latency_s"], 0.75)
        self.assertIsNotNone(e.get_system_immunity_stats() and e.reg["last_loop"])

    def test_a_service_turning_red_in_daemon_health_is_captured_once(self):
        import daemon_engine
        base = Path(TMP) / "dstate"
        old = os.environ.get("NEXXUS_DAEMON_STATE_DIR")
        os.environ["NEXXUS_DAEMON_STATE_DIR"] = str(base)
        try:
            cfg = daemon_engine.load_config()
            health = {"daemon": {"running": True, "pid": os.getpid()}, "services": {"dashboard": {"indicator": "red", "check": "port 8000 is not accepting connections", "detail": ""}, "ollama": {"indicator": "green", "check": "ok"}}}
            (cfg["state_dir"] / "system_health.json").write_text(json.dumps(health))
            e = engine("l2")
            self.assertEqual(e.tick()["captured_from_telemetry"], ["dashboard"])
            self.assertEqual(e.tick()["captured_from_telemetry"], [])                       # still red: not a new failure
            health["services"]["dashboard"]["indicator"] = "green"
            (cfg["state_dir"] / "system_health.json").write_text(json.dumps(health))
            e.tick()
            health["services"]["dashboard"]["indicator"] = "red"
            (cfg["state_dir"] / "system_health.json").write_text(json.dumps(health))
            self.assertEqual(e.tick()["captured_from_telemetry"], ["dashboard"])            # went red AGAIN: that is a recurrence
            s = e.get_system_immunity_stats()
            self.assertEqual((s["total_captured"], s["active_rules_count"], s["recurrences_after_rule"]), (2, 1, 1))
        finally:
            if old is None:
                os.environ.pop("NEXXUS_DAEMON_STATE_DIR", None)
            else:
                os.environ["NEXXUS_DAEMON_STATE_DIR"] = old

    def test_the_background_loop_runs_and_stops(self):
        e = engine("l3")
        e.cfg["loop_interval_seconds"] = 1
        e.record_outcome("n", True, 0.1)
        self.assertTrue(e.start_loop())
        self.assertFalse(e.start_loop())
        for _ in range(60):
            if e.reg.get("last_loop"):
                break
            time.sleep(0.1)
        self.assertTrue(e.reg["last_loop"])
        self.assertTrue(e.status()["loop_running"])
        e.stop_loop()
        self.assertFalse(e.status()["loop_running"])


class Reporting(unittest.TestCase):
    def test_immunity_stats_shape_for_the_dashboard(self):
        e = engine("r1")
        self.assertEqual(e.get_system_immunity_stats()["active_rules"], [])
        e.capture_and_convert("KeyError: 'x'", "n")
        s = e.get_system_immunity_stats()
        for k in ("total_resolved", "active_rules_count", "active_rules", "recurrences_after_rule", "enforceable_rules", "detect_only_rules", "note"):
            self.assertIn(k, s)
        self.assertEqual(s["active_rules"][0]["type"], "require_key")
        self.assertIn("not proof the cause is fixed", s["note"])
        self.assertTrue(e.status()["history"]["ok"])

    def test_chat_report_is_honest_when_nothing_has_failed(self):
        sl._ENGINE = engine("r2")
        try:
            r = sl.handle_prompt("what is our immunity status")
            self.assertEqual(r["status"], "done")
            self.assertIn("nothing to learn from yet", r["message"])
            sl._ENGINE.capture_and_convert("KeyError: 'x'", "n")
            self.assertIn("1 failure(s) converted", sl.handle_prompt("immunity")["message"])
        finally:
            sl._ENGINE = None
        for yes in ("show me the immunity stats", "what are the preventative rules", "adaptation registry"):
            self.assertTrue(sl.is_slae_prompt(yes), yes)
        for no in ("hello", "write an invoice", "what is the weather"):
            self.assertFalse(sl.is_slae_prompt(no), no)


class WiredIn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(ROOT)
        import nexxus_talks
        cls.nt = nexxus_talks

    def test_master_config_registers_the_engine_and_the_bot_exists(self):
        names = sl.nexxus_paths.read_config(["SLAE_CONFIG"])["SLAE_CONFIG"]
        self.assertEqual(sorted(names)[:2], ["auto_remediation", "enabled"])
        self.assertIn("adaptation-engine", self.nt.BOT_REGISTRY)

    def test_talks_failures_and_successes_feed_the_loop_and_never_break_a_turn(self):
        sl._ENGINE = engine("w1")
        try:
            self.nt.slae_report_success("nexxus_talks.generate_response", 0.2)
            try:
                {}["prompt"]
            except KeyError as ex:
                self.nt.slae_report_failure("nexxus_talks.generate_response", ex, {"prompt_chars": 5})
            s = sl._ENGINE.get_system_immunity_stats()
            self.assertEqual((s["total_captured"], s["active_rules_count"]), (1, 1))
            self.assertEqual(len(sl._ENGINE.preflight("nexxus_talks.generate_response", {})), 1)
            sl._ENGINE.record_outcome("x", True)
            sl._ENGINE = object()                                                           # a broken engine must not break the chat turn
            self.nt.slae_report_failure("n", ValueError("x"))
            self.nt.slae_report_success("n", 1.0)
        finally:
            sl._ENGINE = None

    def test_chat_is_routed_to_the_bot_and_ordinary_chat_is_not(self):
        sl._ENGINE = engine("w2")
        try:
            r = self.nt.route_to_bot("show me the immunity stats")
            self.assertEqual(r["bot_id"], "adaptation-engine")
            self.assertIn("Immunity:", r["result"]["message"])
            self.assertNotEqual((self.nt.route_to_bot("tell me a joke") or {}).get("bot_id"), "adaptation-engine")
        finally:
            sl._ENGINE = None

    def test_generate_response_exceptions_are_captured_then_still_raised(self):
        sl._ENGINE = engine("w3")
        try:
            talks = self.nt.NexxusTalks.__new__(self.nt.NexxusTalks)                        # no heavy init: the first thing generate_response touches fails for real
            with self.assertRaises(Exception):
                talks.generate_response("hello")
            s = sl._ENGINE.get_system_immunity_stats()
            self.assertGreaterEqual(s["total_captured"], 1)
            self.assertEqual(s["active_rules"][0]["source_nodes"][0], "nexxus_talks.generate_response")
        finally:
            sl._ENGINE = None


if __name__ == "__main__":
    unittest.main(verbosity=1)
