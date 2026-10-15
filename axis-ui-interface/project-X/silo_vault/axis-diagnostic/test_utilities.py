"""test_utilities.py - the six axis-diagnostic utilities that used to only print now do real work. Run: python test_utilities.py (temporary data folder)"""
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

DATA = tempfile.mkdtemp(prefix="diag_")
os.environ["AXIS_DIAGNOSTIC_DATA"] = DATA
os.environ.setdefault("NEXXUS_MESH_URL", "http://127.0.0.1:9")
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from src import diag_store as store  # noqa: E402
from src.governor.governor_override_utility import governoroverrideutility, sign  # noqa: E402
from src.governor.governor_sync_utility import governorsyncutility  # noqa: E402
from src.maintenance_learning_utility import maintenancelearningutility  # noqa: E402
from src.pattern_alert_utility import patternalertutility  # noqa: E402
from src.root_registry_utility import rootregistryutility  # noqa: E402
from src.telemetry_fire_forget_utility import telemetryfireforgetutility  # noqa: E402


def cfg(**kw):
    return type("C", (), kw)()


class Base(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(DATA, ignore_errors=True)
        os.makedirs(DATA)


class Learning(Base):
    def test_the_model_learns_normal_and_reports_surprise_before_learning(self):
        m = maintenancelearningutility(cfg(learning_rate=0.2, model_version="2.0.4"))
        first = m.update_model({"cpu": 40.0, "bad": "x", "nan": float("nan"), "flag": True})
        self.assertEqual((first["updated"], sorted(first["ignored"]), first["surprise"]["cpu"]), (["cpu"], ["bad", "flag", "nan"], None))
        for v in (41, 39, 40, 42, 38, 40, 41, 39):
            r = m.update_model({"cpu": float(v)})
        self.assertLess(abs(r["surprise"]["cpu"]), 3)
        spike = m.update_model({"cpu": 95.0})
        self.assertGreater(spike["surprise"]["cpu"], 5)                                # far from normal: a big surprise
        self.assertEqual(store.read_json("maintenance_model")["samples"], 10)           # persisted, not just remembered
        with self.assertRaises(TypeError):
            m.update_model([1, 2])


class Alerts(Base):
    def test_sensitivity_and_debounce_decide_what_is_raised_and_all_of_it_is_recorded(self):
        a = patternalertutility(cfg(sensitivity="medium", alert_channel="sys_log_alert", debounce_ms=10000))
        self.assertFalse(a.trigger("p1", "low"))                                       # below medium
        self.assertTrue(a.trigger("p1", "high"))
        self.assertFalse(a.trigger("p1", "critical"))                                  # same pattern within the debounce window
        self.assertTrue(a.trigger("p2", "medium"))
        rows = store.read_jsonl("sys_log_alert")
        self.assertEqual([r["raised"] for r in rows], [False, True, False, True])
        self.assertIn("below sensitivity", rows[0]["suppressed_because"])
        self.assertIn("repeat", rows[2]["suppressed_because"])
        with self.assertRaises(ValueError):
            a.trigger("p", "catastrophic")
        with self.assertRaises(ValueError):
            patternalertutility(cfg(sensitivity="max", alert_channel="c", debounce_ms=0)).trigger("p", "low")


class Registry(Base):
    def test_entries_need_real_files_carry_hashes_and_changes_are_detected(self):
        r = rootregistryutility(cfg(registry_path="/sys/registry/root", access_level="admin"))
        f = os.path.join(DATA, "a.txt")
        open(f, "w").write("one")
        e = r.register_entry("alpha", f)
        self.assertEqual((e["key"], e["bytes"], len(e["sha256"])), ("alpha", 3, 64))
        self.assertTrue(os.path.isfile(os.path.join(DATA, "sys", "registry", "root.json")))        # the unix-style path stayed inside the data folder
        self.assertTrue(r.verify()["ok"])
        open(f, "w").write("two!")
        self.assertIn("changed", r.verify()["problems"][0])
        g = os.path.join(DATA, "b.txt")
        open(g, "w").write("x")
        with self.assertRaises(ValueError):
            r.register_entry("alpha", g)                                               # key already bound to another existing file
        with self.assertRaises(FileNotFoundError):
            r.register_entry("beta", os.path.join(DATA, "nope"))
        with self.assertRaises(PermissionError):
            rootregistryutility(cfg(registry_path="r", access_level="guest")).register_entry("k", f)


class Telemetry(Base):
    def test_the_local_bus_receives_packets_and_nothing_leaves_the_machine(self):
        t = telemetryfireforgetutility(cfg(endpoint="internal_bus://telemetry", priority="low", buffer_size=5))
        self.assertTrue(t.dispatch({"cpu": 1})["queued"])
        self.assertEqual(store.read_jsonl("internal_bus/telemetry")[0]["packet"], {"cpu": 1})
        self.assertTrue(t.dispatch({"s": {1, 2}})["queued"])                             # not JSON natively, but turned into text rather than refused
        remote = telemetryfireforgetutility(cfg(endpoint="https://example.com/collect", priority="low", buffer_size=5))
        r = remote.dispatch({"a": 1})
        self.assertEqual((r["queued"], r["why"]), (False, "endpoint is not local"))
        self.assertEqual(store.read_jsonl("telemetry_outcomes")[-1]["status"], "refused")
        with self.assertRaises(ValueError):
            telemetryfireforgetutility(cfg(endpoint="internal_bus://t", priority="urgent")).dispatch({})

    def test_a_loopback_endpoint_gets_the_post_in_the_background_and_failures_are_recorded_not_raised(self):
        got = []

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            t = telemetryfireforgetutility(cfg(endpoint="http://127.0.0.1:%d/t" % srv.server_port, priority="high", buffer_size=5))
            self.assertTrue(t.dispatch({"hello": 1})["queued"])
            for _ in range(50):
                if got:
                    break
                time.sleep(0.05)
            self.assertEqual(got[0]["packet"], {"hello": 1})
            self.assertEqual(got[0]["priority"], "high")
        finally:
            srv.shutdown()
        dead = telemetryfireforgetutility(cfg(endpoint="http://127.0.0.1:9/t", priority="low", buffer_size=5))
        self.assertTrue(dead.dispatch({"a": 1})["queued"])                              # the caller is never told about delivery problems...
        for _ in range(80):
            rows = store.read_jsonl("telemetry_outcomes")
            if any(r["status"] == "failed" for r in rows):
                break
            time.sleep(0.05)
        self.assertTrue(any(r["status"] == "failed" for r in store.read_jsonl("telemetry_outcomes")))      # ...but the log is

    def test_the_buffer_limit_drops_and_says_so(self):
        t = telemetryfireforgetutility(cfg(endpoint="internal_bus://x", priority="low", buffer_size=0))
        self.assertEqual(t.dispatch({"a": 1}), {"queued": False, "why": "buffer full"})
        self.assertEqual(store.read_jsonl("telemetry_outcomes")[-1]["status"], "dropped")


class Governor(Base):
    def _peer(self, state):
        store.write_json("nodes/n1/state", state)

    def test_sync_takes_the_newer_entry_each_way_and_modes_are_respected(self):
        store.write_json("local_state", {"a": {"value": 1, "at": "2026-01-02"}, "only_local": {"value": 9, "at": "2026-01-01"}})
        self._peer({"a": {"value": 2, "at": "2026-01-03"}, "only_peer": {"value": 5, "at": "2026-01-01"}})
        s = governorsyncutility(cfg(sync_mode="bidirectional", latency_threshold=60000, auto_reconnect=True)).synchronize("n1")
        self.assertEqual((s["status"], s["pulled"], s["pushed"]), ("synchronized", ["a", "only_peer"], ["only_local"]))
        self.assertEqual(store.read_json("local_state")["a"]["value"], 2)
        self.assertEqual(store.read_json("nodes/n1/state")["only_local"]["value"], 9)
        self.assertEqual(governorsyncutility(cfg(sync_mode="bidirectional", latency_threshold=60000)).synchronize("n1")["status"], "in_sync")
        store.write_json("local_state", {"x": {"value": 1, "at": "2026-02-01"}})
        self._peer({"y": {"value": 1, "at": "2026-02-01"}})
        p = governorsyncutility(cfg(sync_mode="pull", latency_threshold=60000)).synchronize("n1")
        self.assertEqual((p["pulled"], p["pushed"]), (["y"], []))
        self.assertEqual(governorsyncutility(cfg(sync_mode="bidirectional", latency_threshold=60000)).synchronize("ghost")["status"], "no_peer_state")
        with self.assertRaises(ValueError):
            governorsyncutility(cfg(sync_mode="telepathy", latency_threshold=1)).synchronize("n1")
        with self.assertRaises(ValueError):
            governorsyncutility(cfg(sync_mode="pull", latency_threshold=1)).synchronize("../x")

    def test_a_slow_peer_is_reported_stale(self):
        self._peer({"k": {"value": 1, "at": "2026-01-01"}})
        time.sleep(0.05)
        self.assertTrue(governorsyncutility(cfg(sync_mode="pull", latency_threshold=1)).synchronize("n1")["stale"])

    def test_overrides_need_a_secret_a_signature_and_an_allowed_command(self):
        o = governoroverrideutility(cfg(override_level="full_system_access", require_authorization=True, audit_log_override=True))
        os.environ.pop("AXIS_OVERRIDE_SECRET", None)
        r = o.execute_override("n1", "restart", "anything")
        self.assertEqual(r["status"], "refused")
        self.assertIn("no AXIS_OVERRIDE_SECRET", r["why"])
        os.environ["AXIS_OVERRIDE_SECRET"] = "s3cret-value"
        try:
            self.assertIn("missing or wrong", o.execute_override("n1", "restart", "bad")["why"])
            self.assertIn("not one of", o.execute_override("n1", "rm -rf /", sign("n1", "rm -rf /", "s3cret-value"))["why"])
            self.assertEqual(o.execute_override("n1", "pause", sign("n1", "pause", "s3cret-value"))["status"], "queued")
            self.assertEqual(o.execute_override("n1", "pause", sign("n2", "pause", "s3cret-value"))["status"], "refused")     # a signature is for one node and one command
        finally:
            os.environ.pop("AXIS_OVERRIDE_SECRET", None)
        self.assertEqual(store.read_jsonl("nodes/n1/commands")[0]["command"], "pause")
        self.assertEqual([r["status"] for r in store.read_jsonl("override_audit")], ["refused", "refused", "refused", "queued", "refused"])
        open_o = governoroverrideutility(cfg(override_level="x", require_authorization=False, audit_log_override=False))
        self.assertEqual(open_o.execute_override("n9", "flush")["status"], "queued")
        self.assertEqual(open_o.execute_override("../n", "flush")["status"], "refused")


if __name__ == "__main__":
    unittest.main(verbosity=1, warnings="ignore")
