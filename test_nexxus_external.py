"""NEXXUS's connector for independent modules: signs correctly, stays on this computer, and can be removed by deleting a file."""
import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import nexxus_external as ne

KEY = "k" * 40
SEEN = []


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        pkt = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append((self.headers["Host"], pkt))
        body = json.dumps({k: v for k, v in pkt.items() if k != "signature"}, sort_keys=True).encode()
        good = hmac.compare_digest(hmac.new(KEY.encode(), body, hashlib.sha256).hexdigest(), pkt.get("signature", ""))
        fresh = abs(time.time() - pkt.get("ts", 0)) < 60 and pkt.get("origin") == "NEXXUS_EXECUTOR"
        if not (good and fresh):
            code, out = 401, {"status": "error", "error": "unauthorized"}
        elif pkt["op"] == "utilities":
            code, out = 200, {"status": "success", "result": {"status": {"description": "d", "params": {}, "build": False, "chat_ok": True},
                                                             "danger": {"description": "builds", "params": {}, "build": True, "chat_ok": False},
                                                             "admin": {"description": "needs token", "params": {}, "build": False, "chat_ok": False}}}
        elif pkt["op"] == "health":
            code, out = 200, {"status": "success", "result": {"ok": True}}
        else:
            code, out = 200, {"status": "success", "result": {"ran": pkt["utility"], "args": pkt["args"]}}
        data = json.dumps(out).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def mod(tmp_path, monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    folder = tmp_path / "mod"; folder.mkdir()
    (folder / "nexxus.secret").write_text(KEY)
    cfg = tmp_path / "external_modules.json"
    cfg.write_text(json.dumps({"_generated_by": "x", "mod": {"base": f"http://127.0.0.1:{srv.server_address[1]}", "host": "mod.localhost:8080", "path": "/rpc", "secret_file": str(folder / "nexxus.secret")}}))
    monkeypatch.setattr(ne, "CONFIG", cfg)
    monkeypatch.delenv("NEXXUS_MODULE_SECRET_MOD", raising=False)
    SEEN.clear()
    yield type("M", (), {"cfg": cfg, "folder": folder, "srv": srv})
    srv.shutdown()


def test_discovery_call_and_probe_use_signed_requests_with_the_gateway_host_header(mod):
    utils = {}
    d = ne.discover("mod", utils)
    assert d["status"] == "success" and utils["mod"]["external"] is True
    posted = []
    r = ne.call("mod", "status", {"a": 1}, 30, False, True, utils, lambda *a: posted.append(a))
    assert r["status"] == "success" and r["result"] == {"ran": "status", "args": {"a": 1}} and posted
    assert ne.probe("mod", deep=True)["health"] == {"ok": True}
    assert all(host == "mod.localhost:8080" for host, _ in SEEN)


def test_build_and_chat_rules_are_enforced_before_anything_is_sent(mod):
    utils = {}
    ne.discover("mod", utils)
    sent = len(SEEN)
    assert "build utility" in ne.call("mod", "danger", {}, 30, False, False, utils, lambda *a: None)["error"]
    assert "not enabled for chat" in ne.call("mod", "admin", {}, 30, False, True, utils, lambda *a: None)["error"]
    assert "declares no utility" in ne.call("mod", "wipe", {}, 30, False, False, utils, lambda *a: None)["error"]
    assert "JSON object" in ne.call("mod", "status", ["not", "a", "dict"], 30, False, False, utils, lambda *a: None)["error"]
    assert len(SEEN) == sent


def test_only_this_computer_and_only_a_tiny_nexxus_secret_file_are_accepted(mod):
    cfg = json.loads(mod.cfg.read_text())
    cfg["mod"]["base"] = "http://example.com"
    mod.cfg.write_text(json.dumps(cfg))
    assert "must be on this computer" in ne.discover("mod", {})["error"]
    cfg["mod"]["base"] = f"http://127.0.0.1:{mod.srv.server_address[1]}"
    cfg["mod"]["secret_file"] = str(mod.folder.parent / "other.txt")
    (mod.folder.parent / "other.txt").write_text(KEY)
    mod.cfg.write_text(json.dumps(cfg))
    assert "no usable secret" in ne.discover("mod", {})["error"]                  # not named nexxus.secret
    cfg["mod"]["secret_file"] = str(mod.folder / "nexxus.secret")
    (mod.folder / "nexxus.secret").write_text("short")
    mod.cfg.write_text(json.dumps(cfg))
    assert "no usable secret" in ne.discover("mod", {})["error"]


def test_removing_a_module_from_the_published_list_makes_nexxus_forget_it(mod):
    utils = {}
    ne.discover("mod", utils)
    assert ne.is_external("mod") and ne.names() == ["mod"]
    mod.cfg.write_text(json.dumps({"_generated_by": "x"}))                       # the gateway re-published without it
    assert not ne.is_external("mod") and ne.names() == []
    ne.prune(utils)
    assert "mod" not in utils


def test_a_wrong_secret_is_refused_by_the_module_and_reported(mod):
    (mod.folder / "nexxus.secret").write_text("z" * 40)
    assert ne.discover("mod", {})["status"] == "error"
