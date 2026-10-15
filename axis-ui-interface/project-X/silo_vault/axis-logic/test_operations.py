"""test_operations.py - axis-logic's governor, watchdog, port, emergency halt and engine bridge really do their jobs. Run: python test_operations.py"""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("NEXXUS_MESH_URL", "http://127.0.0.1:9")
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Governor(unittest.TestCase):
    def setUp(self):
        self.bg = load("operations/build_governor.py", "bg").BuildGovernor(os.path.join(ROOT, "operations", "config", "build_governor_config.py"))

    def test_only_allowed_commands_with_clean_data_run(self):
        g = self.bg
        self.assertTrue(g.validate_command("sync", {"target": "vault"}))
        self.assertEqual(g.last_reason, "allowed")
        self.assertFalse(g.validate_command("format_disk", {}))
        self.assertIn("restricted", g.last_reason)
        self.assertFalse(g.validate_command("launch_missiles", {}))
        self.assertIn("not an allowed operation", g.last_reason)
        self.assertFalse(g.validate_command("sync", {"api_key": "x"}))
        self.assertIn("secret-looking key", g.last_reason)
        self.assertFalse(g.validate_command("sync", {"files": ["a", "../../etc/passwd"]}))
        self.assertIn("path traversal", g.last_reason)
        self.assertFalse(g.validate_command("sync", "not a dict"))
        self.assertFalse(g.validate_command("", {}))
        self.assertFalse(g.validate_command(None, {}))

    def test_a_missing_config_allows_nothing(self):
        g = load("operations/build_governor.py", "bg2").BuildGovernor("/no/such/config.py")
        self.assertFalse(g.validate_command("sync", {}))
        self.assertIn("nothing is allowed", g.last_reason)

    def test_a_restricted_command_stays_refused_even_if_also_allowed(self):
        p = os.path.join(tempfile.mkdtemp(), "c.py")
        open(p, "w").write('{"restricted_commands": ["sync"], "allowed_operations": ["sync"], "governance_settings": {"enforce_strict_mode": False}}')
        g = load("operations/build_governor.py", "bg3").BuildGovernor(p)
        self.assertFalse(g.validate_command("sync", None))


class Watchdog(unittest.TestCase):
    def test_named_engines_need_heartbeats_and_unknown_is_not_nominal(self):
        W = load("lib/watchdog.py", "wd").Watchdog
        t = [1000.0]
        d = tempfile.mkdtemp()
        w = W(["Volatility", "Trend", "Reversion"], heartbeat_dir=os.path.join(d, "hb"), timeout=60, clock=lambda: t[0])
        self.assertEqual(w.initiate_heartbeat(), {"nominal": [], "failed": [], "unknown": ["Volatility", "Trend", "Reversion"]})
        w.beat("Volatility")
        w.beat("Trend")
        t[0] += 30
        w.beat("Trend")
        t[0] += 45                                                                         # Volatility last beat 75 s ago, Trend 45 s ago
        r = w.initiate_heartbeat()
        self.assertEqual((r["nominal"], r["failed"], r["unknown"]), (["Trend"], ["Volatility"], ["Reversion"]))
        self.assertIn("Engine Volatility failure", open(os.path.join(d, "watchdog.log")).read())

    def test_engine_objects_are_asked_directly_and_a_crash_counts_as_failed(self):
        W = load("lib/watchdog.py", "wd2").Watchdog

        class E:
            def __init__(self, name, alive):
                self.name, self._a = name, alive

            def is_alive(self):
                if self._a == "crash":
                    raise RuntimeError("x")
                return self._a
        w = W([E("a", True), E("b", False), E("c", "crash")], heartbeat_dir=os.path.join(tempfile.mkdtemp(), "hb"))
        r = w.initiate_heartbeat()
        self.assertEqual((r["nominal"], r["failed"]), (["a"], ["b", "c"]))

    def test_the_silo_watchdogs_no_longer_run_at_import_and_report_honestly(self):
        for silo in ("ecom", "sports", "stocks", "logs"):
            mod = load("%s/lib/watchdog.py" % silo, "silo_wd_" + silo)                    # importing used to crash or run the check
            r = mod.run()
            self.assertEqual(r["nominal"], [])
            self.assertEqual(len(r["unknown"]) + len(r["failed"]), 3)


class Port(unittest.TestCase):
    def test_packets_arrive_over_loopback_and_bad_lines_are_kept_not_dropped(self):
        P = load("lib/port.py", "port").SystemPort
        p = P(0)
        self.assertFalse(p.listen())                                                       # not open yet
        self.assertTrue(p.open_connection())
        self.assertGreater(p.port_number, 0)
        self.assertTrue(p.listen())
        self.assertFalse(p.listen())
        try:
            with socket.create_connection(("127.0.0.1", p.port_number), timeout=2) as c:
                c.sendall(b'{"sensor": 1}\nnot json at all\n{"sensor": 2}')
            got = p.receive(timeout=2)
            for _ in range(10):
                if len(got) >= 3:
                    break
                got += p.receive(timeout=0.3)
            self.assertEqual(got[0], {"sensor": 1})
            self.assertEqual(got[1]["error"], "not JSON")
            self.assertEqual(got[2], {"sensor": 2})
        finally:
            p.close()
        self.assertFalse(p.is_open)
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", p.port_number), timeout=0.5)

    def test_a_taken_port_is_an_error(self):
        P = load("lib/port.py", "port2").SystemPort
        a = P(0)
        a.open_connection()
        try:
            with self.assertRaises(OSError):
                P(a.port_number).open_connection()
        finally:
            a.close()


class Halt(unittest.TestCase):
    def _cfg(self, **kw):
        p = os.path.join(tempfile.mkdtemp(), "halt_cfg.json")
        json.dump(kw, open(p, "w"))
        return p

    def test_it_terminates_only_the_processes_it_was_given_and_records_the_halt(self):
        d = tempfile.mkdtemp()
        H = load("operations/emergency_halt.py", "eh").EmergencyHalt
        h = H(self._cfg(terminate_all_subprocesses=True), halt_file=os.path.join(d, "halt.json"), grace=2.0)
        mine = h.register_process(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]))
        done = h.register_process(subprocess.Popen([sys.executable, "-c", "pass"]))
        bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        time.sleep(0.5)
        try:
            r = h.execute_halt("test failure")
            self.assertEqual((r["status"], r["action"]), ("halted", "shutdown_all_processes"))
            self.assertEqual(sorted(r["terminated"] + r["killed"]), [mine.pid])
            self.assertEqual(r["already_stopped"], [done.pid])
            self.assertIsNotNone(mine.poll())
            self.assertIsNone(bystander.poll())                                           # a process it did not start is untouched
            rec = json.load(open(os.path.join(d, "halt.json")))
            self.assertEqual((rec["reason"], rec["status"]), ("test failure", "halted"))
        finally:
            bystander.kill()

    def test_a_process_that_ignores_terminate_is_killed(self):
        stubborn = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(60)"
        if os.name == "nt":                                                                # terminate() is already a hard kill on Windows
            self.skipTest("windows terminate is forceful")
        h = load("operations/emergency_halt.py", "eh2").EmergencyHalt(self._cfg(terminate_all_subprocesses=True), halt_file=os.path.join(tempfile.mkdtemp(), "h.json"), grace=0.5)
        p = h.register_process(subprocess.Popen([sys.executable, "-c", stubborn], stdout=subprocess.PIPE))
        p.stdout.readline()
        self.assertEqual(h.execute_halt("x")["killed"], [p.pid])

    def test_a_partial_halt_isolates_a_node_and_leaves_processes_alone(self):
        h = load("operations/emergency_halt.py", "eh3").EmergencyHalt(self._cfg(terminate_all_subprocesses=False), halt_file=os.path.join(tempfile.mkdtemp(), "h.json"))
        p = h.register_process(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]))
        try:
            with self.assertRaises(ValueError):
                h.execute_halt("x")
            r = h.execute_halt("node failing", node="worker-3")
            self.assertEqual((r["status"], r["isolated"]), ("partial_halt", "worker-3"))
            self.assertIsNone(p.poll())
            self.assertEqual(h.isolated, {"worker-3"})
        finally:
            p.kill()


class Bridge(unittest.TestCase):
    def test_real_silos_are_ready_and_unknown_or_half_built_ones_are_refused(self):
        from src.silo_manager.engine_base import create_bridge
        for name in ("ECOM", "SPORTS", "STOCKS", "LOGS"):
            b = create_bridge(name)
            self.assertEqual(b.check_status(), "READY", name)
            self.assertEqual(b.handshake(), "ACCESS_GRANTED_TO_" + name)
        ghost = create_bridge("GHOST")
        self.assertTrue(ghost.check_status().startswith("NOT_READY"))
        self.assertEqual(ghost.handshake(), "ACCESS_DENIED_TO_GHOST")


if __name__ == "__main__":
    unittest.main(verbosity=1, warnings="ignore")
