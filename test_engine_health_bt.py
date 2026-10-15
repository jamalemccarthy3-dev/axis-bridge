"""test_engine_health_bt.py - two things the last diagnostic run exposed.
(1) Engine health is MEASURED: every engine's mesh.py answers a health probe with real checks (its own file parses, it can sign packets, the hub answers) and reports ok False when one fails; the status
    instruction returns real numbers, not a hard-coded "idle".
(2) Bluetooth says what is wrong: when Windows has no Bluetooth radio the manager reports that in plain words and the panel data shows unavailable until a scan works.
Run: python test_engine_health_bt.py"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SILO = ROOT / "axis-ui-interface" / "project-X" / "silo_vault"
sys.path.insert(0, str(ROOT))


class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"success"}')

    def log_message(self, *a):
        pass


def ask(engine_dir, req, **env):
    e = dict(os.environ, PYTHONPATH=str(ROOT))
    e.update({"NEXXUS_GOVERNANCE_SECRET": "throwaway-secret-for-health-tests", "NEXXUS_ENGINE_INBOX": os.path.join(tempfile.gettempdir(), "nexxus_test_inbox_%s.json" % engine_dir.name)})
    e.update(env)
    r = subprocess.run([sys.executable, "mesh.py", "--mesh"], cwd=str(engine_dir), input=json.dumps(req).encode(), capture_output=True, env=e, timeout=90)
    out = r.stdout.decode().strip()
    assert out, r.stderr.decode()[-400:]
    return json.loads(out.splitlines()[-1])["result"]


class EngineHealth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Ping)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d" % cls.port
        cls.engines = sorted(p.parent for p in SILO.glob("*/mesh.py") if p.parent.name.startswith("axis-") or p.parent.name == "render")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_no_engine_still_has_the_hard_coded_template_health(self):
        self.assertGreaterEqual(len(self.engines), 21)
        for d in self.engines:
            src = (d / "mesh.py").read_text(encoding="utf-8")
            self.assertNotIn("TODO: make this check something real", src.split("def _real_health")[0] if "_real_health" in src else src, d.name)
            self.assertIn("_real_health", src, d.name)

    def test_a_healthy_engine_reports_its_real_checks(self):
        for d in (SILO / "axis-vision", SILO / "axis-triage", SILO / "axis-core"):
            h = ask(d, {"op": "health"}, NEXXUS_MESH_URL=self.url)
            self.assertEqual(h, {"ok": True}, (d.name, h))                                   # healthy is exactly this; the detail lives in health_detail
            detail = ask(d, {"op": "instruct", "instruction": "health_detail"}, NEXXUS_MESH_URL=self.url)
            self.assertIs(detail["ok"], True, (d.name, detail))
            self.assertEqual(detail["engine"], d.name)
            self.assertEqual(set(detail["checks"]), {"entry_file_parses", "can_sign_packets", "hub_reachable"})
            self.assertIn("pid", detail["info"])

    def test_health_goes_false_when_something_real_is_wrong(self):
        d = SILO / "axis-vision"
        dead = socket.socket()
        dead.bind(("127.0.0.1", 0))
        port = dead.getsockname()[1]
        dead.close()
        h = ask(d, {"op": "health"}, NEXXUS_MESH_URL="http://127.0.0.1:%d" % port)
        self.assertIs(h["ok"], False)
        self.assertIs(h["checks"]["hub_reachable"], False)
        self.assertEqual(h["error"], "it cannot reach the NEXXUS hub")                       # plain words
        h = ask(d, {"op": "health"}, NEXXUS_MESH_URL=self.url, NEXXUS_GOVERNANCE_SECRET="")
        self.assertIs(h["ok"], False)
        self.assertIs(h["checks"]["can_sign_packets"], False)
        self.assertIn("cannot sign packets", h["error"])
        for leak in ("Traceback", "RuntimeError", "NEXXUS_GOVERNANCE_SECRET", "\\Users\\"):
            self.assertNotIn(leak, json.dumps(h), leak)
        detail = ask(d, {"op": "instruct", "instruction": "health_detail"}, NEXXUS_MESH_URL=self.url, NEXXUS_GOVERNANCE_SECRET="")
        self.assertEqual(detail["info"]["sign_error"], "RuntimeError")                       # the operator detail names the kind of failure, never the text

    def test_status_returns_real_numbers_and_unknown_instructions_still_say_so(self):
        d = SILO / "axis-link"
        s = ask(d, {"op": "instruct", "instruction": "status"}, NEXXUS_MESH_URL=self.url)
        self.assertEqual(s["state"], "running")
        self.assertIn("pid", s)
        self.assertIn("error", ask(d, {"op": "instruct", "instruction": "dance"}, NEXXUS_MESH_URL=self.url))

    def test_every_engine_answers_the_probe_quickly(self):
        for d in self.engines:
            h = ask(d, {"op": "health"}, NEXXUS_MESH_URL=self.url)
            self.assertIs(h["ok"], True, (d.name, h))


class FakeBackend:
    name = "fake"

    def __init__(self, error=None, found=None):
        self.error, self.found = error, found or []

    @staticmethod
    def available():
        return True, None

    async def scan(self, timeout):
        if self.error:
            raise self.error
        return self.found


class NoRadio(Exception):
    pass


class Bluetooth(unittest.TestCase):
    def manager(self, backend):
        import bluetooth_control as bt
        return bt.BluetoothManager(backend=backend, path=os.path.join(tempfile.mkdtemp(), "devices.json"))

    def test_no_adapter_is_explained_in_plain_words_and_shown_in_the_panel_data(self):
        m = self.manager(FakeBackend(error=NoRadio("('No Bluetooth adapter found', <BleakBluetoothNotAvailableReason.NO_BLUETOOTH: 1>)")))
        with self.assertRaises(RuntimeError) as cm:
            m.scan(2)
        msg = str(cm.exception)
        self.assertIn("no usable Bluetooth radio", msg)
        self.assertIn("Plug in a Bluetooth adapter", msg)
        for leak in ("Traceback", "BleakBluetoothNotAvailableReason", "NO_BLUETOOTH"):
            self.assertNotIn(leak, msg)
        d = m.devices()
        self.assertIs(d["available"], False)
        self.assertIn("no usable Bluetooth radio", d["unavailable_reason"])

    def test_a_working_scan_clears_the_problem_and_lists_what_was_heard(self):
        m = self.manager(FakeBackend(error=NoRadio("No Bluetooth adapter found")))
        with self.assertRaises(RuntimeError):
            m.scan(2)
        m.backend = FakeBackend(found=[{"address": "AA:BB:CC:DD:EE:01", "name": "Test speaker", "rssi": -60}])
        d = m.scan(2)
        self.assertIs(d["available"], True)
        self.assertEqual([x["name"] for x in d["devices"]], ["Test speaker"])
        self.assertEqual(d["devices"][0]["state"], "discovered")

    def test_other_scan_failures_keep_their_own_message(self):
        m = self.manager(FakeBackend(error=RuntimeError("something else broke")))
        with self.assertRaises(RuntimeError) as cm:
            m.scan(2)
        self.assertIn("scan failed", str(cm.exception))
        self.assertIs(m.devices()["available"], True)


class HubJudgesTheAnswer(unittest.TestCase):
    """The hub must not count an engine as healthy just because it ANSWERED: an explicit ok=false is a failed probe."""

    def probe(self, answer):
        import mesh_bridge as mb
        saved = (mb._find_module_file, mb._opted_in, mb._run_engine)
        mb._find_module_file = lambda name: Path(__file__)
        mb._opted_in = lambda path: True
        mb._run_engine = lambda path, req, timeout: (True, answer, 1048576)
        try:
            return mb.probe_engine("axis-core", deep=True)
        finally:
            mb._find_module_file, mb._opted_in, mb._run_engine = saved

    def test_ok_true_passes(self):
        r = self.probe({"ok": True, "checks": {"hub_reachable": True}})
        self.assertEqual(r["status"], "found")
        self.assertIsNone(r["error"])

    def test_ok_false_fails_and_names_the_failed_checks(self):
        r = self.probe({"ok": False, "checks": {"entry_file_parses": True, "can_sign_packets": False, "hub_reachable": False}})
        self.assertEqual(r["status"], "unhealthy")
        self.assertIn("ok=false", r["error"])
        self.assertIn("can_sign_packets", r["error"])
        self.assertIn("hub_reachable", r["error"])
        self.assertNotIn("entry_file_parses", r["error"])

    def test_engines_that_never_said_ok_are_not_broken_by_the_change(self):
        for legacy in ({"state": "idle"}, {"healthy": True}, "alive", None):
            self.assertEqual(self.probe(legacy)["status"], "found", legacy)

    def test_the_diagnostic_follows_the_hub(self):
        src = (SILO / "nexxus" / "mesh_diagnostic.py").read_text(encoding="utf-8")
        self.assertIn('responds = probe_result["status"] == "found"', src)               # so an "unhealthy" status can no longer score as answering


class Tunnel(unittest.TestCase):
    """Share must say WHY it cannot share (Tailscale Serve not enabled on the tailnet) instead of just timing out."""

    def test_serve_not_enabled_is_explained_with_the_approval_link(self):
        import tunnel_control as tc
        status_json = json.dumps({"BackendState": "Running", "Self": {"DNSName": "pc.example.ts.net.", "TailscaleIPs": ["100.64.0.1"], "Online": True}, "Peer": {}})

        def runner(argv, timeout=25):
            if "serve" in argv and "--bg" in argv:
                return 124, "\nServe is not enabled on your tailnet.\nTo enable, visit:\n\n         https://login.tailscale.com/f/serve?node=abc123\n\n", "timed out after 25s"
            if "serve" in argv:
                return 0, "No serve config", ""
            return 0, status_json, ""
        t = tc.TunnelController(runner=runner, exe="tailscale")
        r = t.share()
        self.assertIs(r["ok"], False)
        self.assertEqual(r["action_url"], "https://login.tailscale.com/f/serve?node=abc123")
        self.assertIn("not switched on", r["error"])
        self.assertIn("https://login.tailscale.com/f/serve", r["error"])
        self.assertNotIn("timed out", r["error"])

    def test_a_hung_command_keeps_what_it_printed(self):
        import tunnel_control as tc
        script = "import sys,time; print('Serve is not enabled on your tailnet.', flush=True); time.sleep(30)"
        rc, so, se = tc._default_runner([sys.executable, "-c", script], timeout=2)
        self.assertEqual(rc, 124)
        self.assertIn("Serve is not enabled", so)


if __name__ == "__main__":
    unittest.main(verbosity=1)
