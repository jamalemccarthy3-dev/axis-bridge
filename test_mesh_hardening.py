"""test_mesh_hardening.py - the P0 and P1 hardening of the mesh, checked against the real code.
P0  no outgoing default still says "localhost" (it costs ~2 s per connection on Windows; 127.0.0.1 costs ~4 ms).
P1  honest result envelope (an engine that answers with an error is an error), the standard ping / message handshake with per-pair counters, strict heartbeat validation,
    per-engine derived keys (an engine cannot sign as another; legacy shared-key packets still work until NEXXUS_REQUIRE_ENGINE_KEYS=1), a replay floor at hub start, and liveness that survives a hub restart.
Throwaway secret, folders and files; the real hub is never touched. Run: python test_mesh_hardening.py"""
import atexit
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="meshhard_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = Path(__file__).resolve().parent
SILO = ROOT / "axis-ui-interface" / "project-X" / "silo_vault"
SECRET = "throwaway-secret-for-the-mesh-hardening-tests-0123456789"
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET=SECRET, NEXXUS_UI_ROOT=os.path.join(TMP, "ui"), NEXXUS_BUS_LEDGER=os.path.join(TMP, "ledger.jsonl"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "creations"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"), NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"),
                  NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1", NEXXUS_PUBLISH_DIR=os.path.join(TMP, "pub"), NEXXUS_FACTORY_DIR=os.path.join(TMP, "factory"),
                  NEXXUS_CAMPAIGN_DIR=os.path.join(TMP, "campaigns"), NEXXUS_HOME=os.path.join(TMP, "mount"), NEXXUS_DISABLE_SLAE_LOOP="1", NEXXUS_VAULT_DIR=os.path.join(TMP, "vault"),
                  NEXXUS_DAEMON_STATE_DIR=os.path.join(TMP, "dstate"), NEXXUS_DAEMON_LOG_DIR=os.path.join(TMP, "dlogs"), NEXXUS_DAEMON_ARCHIVE_DIR=os.path.join(TMP, "darch"),
                  NEXXUS_MESH_LIVENESS=os.path.join(TMP, "mesh_liveness.json"))
os.environ.pop("NEXXUS_REQUIRE_ENGINE_KEYS", None)
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SILO / "nexxus"))
import nexxus_governance as gov  # noqa: E402


def body(p):
    return json.dumps({k: v for k, v in p.items() if k != "signature"}, sort_keys=True).encode()


def forged(packet, key, origin):
    """A packet signed with `key`, claiming `origin`: what an attacker who holds one engine's key (or none) could build."""
    p = dict(packet, origin=origin, ts=time.time())
    p["signature"] = hmac.new(key, body(p), hashlib.sha256).hexdigest()
    return p


class P0Localhost(unittest.TestCase):
    def test_no_outgoing_default_says_localhost(self):
        offenders = []
        for f in list(SILO.glob("*/mesh.py")) + list(SILO.glob("*/live_status.py")) + list(SILO.glob("*/nexxus_link.py")):
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"""get\(\s*["']NEXXUS_MESH_URL["']\s*,\s*["']http://localhost""", line):
                    offenders.append("%s:%d" % (f.relative_to(ROOT), i))
        self.assertEqual(offenders, [])
        self.assertIn("NEXXUS_MESH_URL=http://127.0.0.1:8000", (ROOT / "nexxus_env.bat").read_text(encoding="utf-8"))
        for f in (ROOT / "orchestrator_client.py", ROOT / "register_orchestrators.py", ROOT / "portal_chat.py", SILO / "nexxus" / "llm_router.py"):
            self.assertNotRegex(f.read_text(encoding="utf-8").replace("http://localhost:11434", "X", 0), r"""environ\.get\("NEXXUS_(?:MESH|OLLAMA)_URL",\s*"http://localhost""", f.name)
        srv = (ROOT / "python_server.py").read_text(encoding="utf-8")
        self.assertNotIn('"http://localhost:11434/api/generate"', srv)
        self.assertNotIn('or "http://localhost:11434"', srv)

    def test_the_user_facing_address_is_left_alone(self):
        self.assertIn('"http://localhost:8000/"', (ROOT / "axis_bridge.py").read_text(encoding="utf-8"))               # the page the browser opens: still the friendly name


class Identity(unittest.TestCase):
    def test_derived_keys_are_per_engine_and_stable(self):
        a, b = gov.engine_key("axis-vision"), gov.engine_key("axis-core")
        self.assertNotEqual(a, b)
        self.assertEqual(a, gov.engine_key("axis-vision"))
        self.assertNotEqual(a, SECRET.encode())
        self.assertIsNone(gov.engine_key(""))

    def test_an_engine_signature_is_accepted_once(self):
        p = gov.sign_as_engine({"engine": "axis-vision", "state": "running"})
        self.assertEqual(p["origin"], "ENGINE:axis-vision")
        self.assertTrue(gov.validate_engine_packet(p))
        self.assertFalse(gov.validate_engine_packet(p))                                  # single use

    def test_one_engine_cannot_sign_as_another(self):
        key_a = gov.engine_key("axis-vision")
        self.assertFalse(gov.validate_engine_packet(forged({"engine": "axis-core", "state": "running"}, key_a, "ENGINE:axis-core")))      # signed with A's key, claims to be B
        self.assertFalse(gov.validate_engine_packet(forged({"engine": "axis-core", "state": "running"}, key_a, "ENGINE:axis-vision")))    # origin says A, body says B
        self.assertFalse(gov.validate_engine_packet(forged({"engine": "axis-core"}, b"a guess", "ENGINE:axis-core")))
        self.assertTrue(gov.validate_engine_packet(gov.sign_as_engine({"engine": "axis-core"})))                                          # the real B still works

    def test_legacy_shared_key_packets_work_until_strict_mode(self):
        self.assertTrue(gov.validate_engine_packet(gov.sign_command({"engine": "axis-link", "state": "running"})))
        os.environ["NEXXUS_REQUIRE_ENGINE_KEYS"] = "1"
        try:
            self.assertFalse(gov.validate_engine_packet(gov.sign_command({"engine": "axis-link", "state": "running"})))
            self.assertTrue(gov.validate_engine_packet(gov.sign_as_engine({"engine": "axis-link", "state": "running"})))
        finally:
            os.environ.pop("NEXXUS_REQUIRE_ENGINE_KEYS")

    def test_a_packet_from_before_the_hub_started_is_refused(self):
        old = dict({"engine": "axis-sweep", "state": "running"}, origin="ENGINE:axis-sweep", ts=gov.BOOT_TS - 30)
        old["signature"] = hmac.new(gov.engine_key("axis-sweep"), body(old), hashlib.sha256).hexdigest()
        self.assertFalse(gov.validate_engine_packet(old))                                # validly signed and inside the 60 s window, but it predates this process: could be a replay across a restart
        legacy = dict({"engine": "axis-sweep"}, origin="NEXXUS_EXECUTOR", ts=gov.BOOT_TS - 30)
        legacy["signature"] = hmac.new(SECRET.encode(), body(legacy), hashlib.sha256).hexdigest()
        self.assertFalse(gov.validate_engine_packet(legacy))

    def test_the_gate_floor_is_optional_and_default_behaviour_is_unchanged(self):
        import axis_gate
        p = gov.sign_command({"engine": "axis-port"})
        self.assertTrue(axis_gate.check_packet(p, SECRET.encode(), {"NEXXUS_EXECUTOR"}, source="t", channel="T1", max_age=60).allow)
        q = gov.sign_command({"engine": "axis-port", "n": 2})
        self.assertFalse(axis_gate.check_packet(q, SECRET.encode(), {"NEXXUS_EXECUTOR"}, source="t", channel="T2", max_age=60, min_ts=time.time() + 5).allow)

    def test_no_secret_means_nothing_is_accepted(self):
        saved = os.environ.pop("NEXXUS_GOVERNANCE_SECRET")
        try:
            self.assertFalse(gov.validate_engine_packet({"engine": "axis-vision", "origin": "ENGINE:axis-vision", "ts": time.time(), "signature": "0" * 64}))
            with self.assertRaises(RuntimeError):
                gov.sign_as_engine({"engine": "axis-vision"})
        finally:
            os.environ["NEXXUS_GOVERNANCE_SECRET"] = saved


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv, mb
        import python_server as srv  # noqa: E402
        import mesh_bridge as mb  # noqa: E402
        cls.http = srv.app.test_client()
        cls.saved = (mb._find_module_file, mb._opted_in, mb._run_engine)
        cls.saved_msg_file = mb._MSG_FILE
        mb._MSG_FILE = Path(TMP) / "mesh_messages.json"                                 # the message log is a fixed path: without this, stubbed relays were written into the REAL hub log

    def tearDown(self):
        mb._find_module_file, mb._opted_in, mb._run_engine = self.saved

    @classmethod
    def tearDownClass(cls):
        mb._MSG_FILE = cls.saved_msg_file

    def test_the_tests_never_touch_the_real_message_log(self):
        self.assertNotEqual(Path(mb._MSG_FILE).resolve(), (ROOT / "mesh_messages.json").resolve())
        real = ROOT / "mesh_messages.json"
        before = real.stat().st_mtime if real.exists() else None
        self.stub({"ok": True})
        self.relay("ping")
        self.assertEqual(real.stat().st_mtime if real.exists() else None, before)

    def post(self, path, packet):
        return self.http.post(path, json=packet)

    def hb(self, **over):
        return gov.sign_as_engine(dict({"engine": "axis-vision", "state": "running", "interval": 10, "metrics": {"pid": 1}}, **over))

    # -- heartbeat validation and identity on the route
    def test_a_valid_engine_heartbeat_is_recorded(self):
        r = self.post("/api/mesh/status", self.hb())
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertTrue(mb.live_status("axis-vision")["fresh"])

    def test_wrong_key_unsigned_and_impersonation_get_401(self):
        self.assertEqual(self.post("/api/mesh/status", forged({"engine": "axis-core", "state": "running"}, b"x" * 32, "ENGINE:axis-core")).status_code, 401)
        self.assertEqual(self.post("/api/mesh/status", {"engine": "axis-core", "state": "running"}).status_code, 401)
        self.assertEqual(self.post("/api/mesh/status", forged({"engine": "axis-core", "state": "running"}, gov.engine_key("axis-vision"), "ENGINE:axis-core")).status_code, 401)

    def test_legacy_shared_key_heartbeats_still_work_and_strict_mode_refuses_them(self):
        legacy = gov.sign_command({"engine": "axis-link", "state": "running", "interval": 10})
        self.assertEqual(self.post("/api/mesh/status", legacy).status_code, 200)
        os.environ["NEXXUS_REQUIRE_ENGINE_KEYS"] = "1"
        try:
            self.assertEqual(self.post("/api/mesh/status", gov.sign_command({"engine": "axis-link", "state": "running"})).status_code, 401)
            self.assertEqual(self.post("/api/mesh/status", gov.sign_as_engine({"engine": "axis-link", "state": "running"})).status_code, 200)
        finally:
            os.environ.pop("NEXXUS_REQUIRE_ENGINE_KEYS")

    def test_invalid_heartbeat_fields_are_rejected_not_defaulted(self):
        for bad in ({"interval": "fast"}, {"interval": True}, {"interval": 0}, {"interval": 99999}, {"interval": -3}, {"state": ""}, {"state": 7}, {"state": "x" * 80}, {"state": "bad<script>"}, {"metrics": [1, 2]}, {"metrics": "x"}):
            r = self.post("/api/mesh/status", self.hb(**bad))
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("invalid heartbeat", r.get_json()["error"], bad)

    def test_missing_optional_fields_take_the_documented_defaults(self):
        p = gov.sign_as_engine({"engine": "axis-port"})
        self.assertEqual(self.post("/api/mesh/status", p).status_code, 200)
        live = mb.live_status("axis-port")
        self.assertEqual((live["state"], live["interval"]), ("running", 10.0))
        self.assertEqual(self.post("/api/mesh/status", gov.sign_as_engine({"engine": "axis-port", "state": "processing", "interval": 2.5, "metrics": {"queue": 4}})).status_code, 200)
        self.assertEqual((mb.live_status("axis-port")["state"], mb.live_status("axis-port")["interval"]), ("processing", 2.5))

    def test_unknown_engine_is_still_400(self):
        self.assertEqual(self.post("/api/mesh/status", gov.sign_as_engine({"engine": "not-an-engine", "state": "running"})).status_code, 400)

    # -- result envelope and handshake
    def stub(self, answer, ok=True):
        mb._find_module_file = lambda name: Path(__file__)
        mb._opted_in = lambda path: True
        mb._run_engine = lambda path, req, timeout: (ok, answer, None)

    def test_an_engine_error_is_an_error_not_a_success(self):
        self.stub({"error": "unknown instruction 'dance'"})
        out = mb.instruct("axis-core", "dance")
        self.assertEqual(out["status"], "error")
        self.assertIn("unknown instruction", out["error"])
        self.assertEqual(out["result"], {"error": "unknown instruction 'dance'"})
        for good in ({"ok": True}, {"state": "idle"}, {"error": "", "x": 1}, "text", 7):
            self.stub(good)
            self.assertEqual(mb.instruct("axis-core", "status")["status"], "success", good)
        self.stub({"ok": True, "error": "ignored because the engine says ok"})
        self.assertEqual(mb.instruct("axis-core", "status")["status"], "success")

    def relay(self, instruction="ping"):
        pkt = gov.sign_as_engine({"engine": "axis-vision", "kind": "note", "to": "axis-core", "body": {"instruction": instruction, "payload": {"text": "hi"}}})
        return self.post("/api/mesh/message", pkt).get_json()

    def pair(self):
        return next((h for h in mb.handshakes() if (h["from"], h["to"]) == ("axis-vision", "axis-core")), {"sent": 0, "delivered": 0, "acknowledged": 0, "failed": 0})

    def test_a_handled_message_is_acknowledged_counted_and_logged(self):
        before = self.pair()
        self.stub({"ok": True, "engine": "axis-core", "ts": 1.0, "received": True, "from": "axis-vision"})
        r = self.relay("message")
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["handshake"], {"delivered": True, "acknowledged": True})
        after = self.pair()
        self.assertEqual((after["sent"] - before["sent"], after["acknowledged"] - before["acknowledged"], after["failed"] - before["failed"]), (1, 1, 0))
        acks = [m for m in mb.messages(0)[-20:] if m["kind"] == "ack" and m["from"] == "axis-core" and m["to"] == "axis-vision"]
        self.assertTrue(acks)
        t = self.http.get("/api/mesh/telemetry").get_json()
        self.assertTrue(any(h["from"] == "axis-vision" and h["to"] == "axis-core" for h in t["handshakes"]))

    def test_an_unhandled_message_is_delivered_but_not_acknowledged_and_counts_as_failed(self):
        before = self.pair()
        self.stub({"error": "unknown instruction 'message'"})
        r = self.relay("message")
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["handshake"], {"delivered": True, "acknowledged": False})
        after = self.pair()
        self.assertEqual((after["delivered"] - before["delivered"], after["acknowledged"] - before["acknowledged"], after["failed"] - before["failed"]), (1, 0, 1))

    def test_a_crashed_engine_is_not_delivered(self):
        before = self.pair()
        self.stub("engine exited 1: boom", ok=False)
        r = self.relay("ping")
        self.assertEqual(r["handshake"], {"delivered": False, "acknowledged": False})
        self.assertEqual(self.pair()["delivered"], before["delivered"])

    # -- durable liveness
    def test_liveness_survives_a_restart_with_its_real_age(self):
        mb._LIVE.clear()
        mb.record_heartbeat("axis-drive", "running", {"pid": 5}, 10)
        mb._save_live(force=True)
        data = json.loads(Path(os.environ["NEXXUS_MESH_LIVENESS"]).read_text())
        data["engines"]["axis-drive"]["received_at"] = time.time() - 300               # it last reported five minutes ago
        data["engines"]["not-an-engine"] = {"state": "running", "received_at": time.time(), "interval": 10}
        data["engines"]["axis-omni"] = {"state": "running", "received_at": time.time() + 99999, "interval": 10}      # a timestamp from the future is not believed
        Path(os.environ["NEXXUS_MESH_LIVENESS"]).write_text(json.dumps(data))
        mb._LIVE.clear()                                                                # "restart"
        mb._load_live()
        live = mb.live_status("axis-drive")
        self.assertIsNotNone(live)
        self.assertFalse(live["fresh"])
        self.assertGreaterEqual(live["age_s"], 299)
        self.assertIsNone(mb.live_status("not-an-engine"))
        self.assertIsNone(mb.live_status("axis-omni"))
        mb.record_heartbeat("axis-drive", "running", {}, 10)
        self.assertTrue(mb.live_status("axis-drive")["fresh"])                          # and a new heartbeat makes it fresh again

    def test_a_corrupt_liveness_file_is_ignored_and_saves_are_atomic(self):
        Path(os.environ["NEXXUS_MESH_LIVENESS"]).write_text("{ not json")
        mb._LIVE.clear()
        mb._load_live()
        self.assertEqual(mb._LIVE, {})
        mb.record_heartbeat("axis-drive", "running", {}, 10)
        mb._save_live(force=True)
        json.loads(Path(os.environ["NEXXUS_MESH_LIVENESS"]).read_text())
        self.assertEqual([p for p in os.listdir(TMP) if p.endswith(".tmp")], [])


class EngineCode(unittest.TestCase):
    def run_engine(self, name, req, **env):
        e = dict(os.environ, PYTHONPATH=str(ROOT), NEXXUS_ENGINE_INBOX=os.path.join(TMP, "inbox_%s.json" % name))     # the engine's inbox goes to a temp file, never into the real engine folder
        e.update(env)
        r = subprocess.run([sys.executable, "mesh.py", "--mesh"], cwd=str(SILO / name), input=json.dumps(req).encode(), capture_output=True, env=e, timeout=90)
        out = r.stdout.decode().strip()
        self.assertTrue(out, r.stderr.decode()[-300:])
        return json.loads(out.splitlines()[-1])["result"]

    def test_ping_and_message_are_answered_by_every_engine(self):
        names = sorted(p.parent.name for p in SILO.glob("axis-*/mesh.py")) + ["render"]
        self.assertGreaterEqual(len(names), 21)
        for n in names:
            ping = self.run_engine(n, {"op": "instruct", "instruction": "ping"})
            self.assertIs(ping["ok"], True, n)
            self.assertEqual(ping["engine"], n)
            msg = self.run_engine(n, {"op": "instruct", "instruction": "message", "payload": {"from": "axis-vision"}})
            self.assertEqual((msg["ok"], msg["received"], msg["from"]), (True, True, "axis-vision"), n)
        self.assertIn("error", self.run_engine("axis-vision", {"op": "instruct", "instruction": "dance"}))           # unknown instructions still say so

    def test_engines_sign_with_their_own_key_and_the_hub_accepts_it(self):
        code = ("import json, mesh\n"
                "p = mesh._sign({'engine': mesh.ENGINE_NAME, 'state': 'running'})\n"
                "print(json.dumps(p))\n")
        for n in ("axis-vision", "axis-triage", "axis-llm"):
            r = subprocess.run([sys.executable, "-c", code], cwd=str(SILO / n), capture_output=True, env=dict(os.environ, PYTHONPATH=str(ROOT)), timeout=60)
            p = json.loads(r.stdout.decode().strip().splitlines()[-1])
            self.assertEqual(p["origin"], "ENGINE:" + n)
            self.assertTrue(gov.validate_engine_packet(p), n)

    def test_the_health_check_uses_the_same_signing_path(self):
        h = self.run_engine("axis-vision", {"op": "health"}, NEXXUS_MESH_URL="http://127.0.0.1:8000")
        detail = self.run_engine("axis-vision", {"op": "instruct", "instruction": "health_detail"}, NEXXUS_MESH_URL="http://127.0.0.1:8000")
        self.assertIn("can_sign_packets", detail["checks"])
        h = self.run_engine("axis-vision", {"op": "health"}, NEXXUS_GOVERNANCE_SECRET="")
        self.assertIs(h["checks"]["can_sign_packets"], False)

    def test_an_older_governance_copy_falls_back_to_the_shared_key(self):
        d = Path(tempfile.mkdtemp(dir=TMP))
        (d / "nexxus_governance.py").write_text((ROOT / "nexxus_governance.py").read_text(encoding="utf-8").replace("def sign_as_engine", "def _renamed_sign_as_engine"), encoding="utf-8")
        code = ("import sys, json\nsys.path.insert(0, %r)\nsys.path.insert(0, %r)\nimport mesh\np = mesh._sign({'engine': mesh.ENGINE_NAME})\nprint(json.dumps(p))\n" % (str(d), str(SILO / "axis-vision")))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, env=dict(os.environ, PYTHONPATH=""), timeout=60)
        p = json.loads(r.stdout.decode().strip().splitlines()[-1])
        self.assertEqual(p["origin"], "NEXXUS_EXECUTOR")
        self.assertTrue(gov.validate_engine_packet(p))

    def test_the_diagnostic_requires_a_handled_handshake(self):
        src = (SILO / "nexxus" / "mesh_diagnostic.py").read_text(encoding="utf-8")
        self.assertIn("Handled a relayed message", src)
        self.assertIn('m.get("kind") == "ack"', src)


if __name__ == "__main__":
    unittest.main(verbosity=1)
