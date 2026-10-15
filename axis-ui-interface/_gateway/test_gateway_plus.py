"""Tests for the gateway additions: the local-only NEXXUS route (nexxus.localhost), automatic ports ("port": "auto"),
and the private traffic log. The original behaviour is covered by test_gateway.py and must keep passing."""
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import gateway
from test_gateway import BASE, FAKE_MODULE, SECRET, free_port, make_module


# ------------------------------------------------------------------ a stand-in for the NEXXUS bridge (records what reaches it)
def fake_bridge(seen):
    class H(BaseHTTPRequestHandler):
        def _go(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n).decode() if n else ""
            seen.append({"method": self.command, "path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
            data = b"nexxus-bridge-ok"
            self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        do_GET = do_POST = do_DELETE = _go
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def gw(tmp_path):
    seen = []
    bridge = fake_bridge(seen)
    bport = bridge.server_address[1]
    cfg = {"gateway": {"host": "127.0.0.1", "port": 0}, "reserved": {"nexxus_bridge": bport},
           "bridge": {"hostnames": ["nexxus.localhost"], "port": bport, "local_only": True, "proxy_timeout": 10}, "modules": {}}
    assert gateway.validate(cfg) == []
    bus = gateway.BusLog(str(tmp_path / "bus.jsonl"))
    reg = gateway.Registry(cfg, buslog=bus)
    srv = gateway.make_server(cfg, registry=reg)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield type("G", (), {"url": f"http://127.0.0.1:{srv.server_address[1]}", "seen": seen, "bus": tmp_path / "bus.jsonl", "cfg": cfg, "reg": reg})
    srv.shutdown(); bridge.shutdown()


def call(g, path="/", host="nexxus.localhost:8080", method="GET", body=None, headers=None):
    req = urllib.request.Request(g.url + path, data=body, method=method, headers={"Host": host, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def bus_lines(g):
    return [json.loads(x) for x in open(g.bus, encoding="utf-8").read().splitlines()] if os.path.exists(g.bus) else []


# ================================================================== 1. NEXXUS through the front door, this computer only
def test_nexxus_is_reachable_through_its_own_hostname_from_this_computer(gw):
    st, body = call(gw, "/api/mode")
    assert (st, body) == (200, "nexxus-bridge-ok") and gw.seen[-1]["path"] == "/api/mode"


def test_the_admin_token_header_and_body_pass_through_to_nexxus(gw):
    st, _ = call(gw, "/api/creations", method="POST", body=b'{"a": 1}', headers={"X-Nexxus-Admin-Token": "tok-123", "Content-Type": "application/json"})
    assert st == 200 and gw.seen[-1]["headers"]["x-nexxus-admin-token"] == "tok-123" and gw.seen[-1]["body"] == '{"a": 1}'


@pytest.mark.parametrize("hint", ["X-Forwarded-For", "X-Forwarded-Host", "X-Real-IP", "Forwarded", "CF-Connecting-IP", "CF-Ray", "CDN-Loop", "True-Client-IP",
                                  "Tailscale-User-Login", "Tailscale-User-Name", "X-Original-Forwarded-For"])
def test_nexxus_refuses_anything_that_arrived_through_a_tunnel_or_proxy(gw, hint):
    before = len(gw.seen)
    st, body = call(gw, "/api/mode", headers={hint: "1.2.3.4"})
    assert st == 404 and body == "Unknown host" and len(gw.seen) == before        # same plain 404 as an unknown host; NEXXUS never saw it


def test_is_outside_decides_by_headers_and_by_address():
    assert gateway.is_outside({}, "192.168.1.5") is True and gateway.is_outside({}, "100.101.102.103") is True
    assert gateway.is_outside({}, "127.0.0.1") is False and gateway.is_outside({}, "::1") is False
    assert gateway.is_outside({"cf-ray": "x"}, "127.0.0.1") is True


def test_cross_site_posts_to_nexxus_are_refused_but_its_own_pages_work(gw):
    before = len(gw.seen)
    st, _ = call(gw, "/api/x", method="POST", body=b"{}", headers={"Origin": "http://evil.example"})
    assert st == 403 and len(gw.seen) == before
    st, _ = call(gw, "/api/x", method="POST", body=b"{}", headers={"Origin": "http://nexxus.localhost:8080"})
    assert st == 200
    st, _ = call(gw, "/api/x", method="DELETE", headers={"Origin": "http://localhost:3000"})
    assert st == 403


def test_other_hostnames_cannot_reach_nexxus(gw):
    for host in ("evil.example", "localhost.evil.example", "nexxus.localhost.evil.example", "blog.localhost:8080"):
        st, body = call(gw, "/api/mode", host=host)
        assert st == 404 and not gw.seen


def test_status_reports_the_nexxus_route(gw):
    st, body = call(gw, "/_status", host="localhost")
    assert st == 200 and json.loads(body)["bridge"] == {"hostnames": ["nexxus.localhost"], "up": True}


def test_validation_will_not_allow_a_nexxus_route_that_is_not_local_only_or_clashes():
    good = {"gateway": {"port": 8080}, "reserved": {"nexxus_bridge": 8000}, "bridge": {"hostnames": ["nexxus.localhost"], "port": 8000, "local_only": True}, "modules": {}}
    assert gateway.validate(good) == []
    assert any("local_only" in e for e in gateway.validate(dict(good, bridge=dict(good["bridge"], local_only=False))))
    assert any("local_only" in e for e in gateway.validate(dict(good, bridge={k: v for k, v in good["bridge"].items() if k != "local_only"})))
    assert any("reserved nexxus_bridge port" in e for e in gateway.validate(dict(good, bridge=dict(good["bridge"], port=9999))))
    assert any("clashes" in e for e in gateway.validate(dict(good, bridge=dict(good["bridge"], hostnames=["localhost"]))))
    clash = dict(good, modules={"blog": {"type": "app", "hostnames": ["nexxus.localhost"], "port": 8701}})
    assert any("nexxus.localhost" in e for e in gateway.validate(clash))
    assert any("reserved for nexxus_bridge" in e for e in gateway.validate(dict(good, modules={"x": {"type": "app", "hostnames": ["x.localhost"], "port": 8000}})))   # modules still cannot take 8000


def test_the_real_config_has_the_local_only_route_and_is_valid():
    cfg = gateway.load_config()
    assert cfg["bridge"]["local_only"] is True and cfg["bridge"]["hostnames"] == ["nexxus.localhost"] and gateway.validate(cfg) == []


# ================================================================== 2. automatic ports
def test_auto_ports_are_in_range_distinct_and_remembered(tmp_path):
    path = str(tmp_path / "auto.json")
    a = gateway.AutoPorts(path)
    p1 = a.assign("alpha", "port", set(), lambda p: False)
    p2 = a.assign("beta", "port", {p1}, lambda p: False)
    assert gateway.AUTO_RANGE[0] <= p1 <= gateway.AUTO_RANGE[1] and p1 != p2
    again = gateway.AutoPorts(path)                                              # a restart: same answers
    assert again.assign("alpha", "port", set(), lambda p: False) == p1 and again.assign("beta", "port", {p1}, lambda p: False) == p2


def test_auto_ports_skip_ports_that_are_in_use_or_claimed(tmp_path, monkeypatch):
    a = gateway.AutoPorts(str(tmp_path / "auto.json"))
    first = a.assign("m1", "port", set(), lambda p: False)
    busy = socket.socket(); busy.bind(("127.0.0.1", first)); busy.listen(1)       # something else grabbed it
    try:
        fresh = gateway.AutoPorts(str(tmp_path / "auto2.json"))
        fresh.data = {"m1": {"port": first}}
        assert fresh.assign("m1", "port", set(), lambda p: False) != first        # saved port is busy and nobody answers there: pick another
        assert gateway.AutoPorts(str(tmp_path / "auto3.json")).assign("m1", "port", {first}, lambda p: False) != first    # claimed by another module
        fresh2 = gateway.AutoPorts(str(tmp_path / "auto4.json")); fresh2.data = {"m1": {"port": first}}
        assert fresh2.assign("m1", "port", set(), lambda p: True) == first         # busy BECAUSE the module itself is running there: keep it
    finally:
        busy.close()


def test_auto_ports_report_a_full_range(tmp_path, monkeypatch):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]
    try:
        monkeypatch.setattr(gateway, "AUTO_RANGE", (p, p))
        assert gateway.AutoPorts(str(tmp_path / "a.json")).assign("m", "port", set(), lambda x: False) is None
    finally:
        s.close()


AUTO_MODULE = '''
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        d = ":".join([os.environ["NEXXUS_MODULE_NAME"], os.environ["NEXXUS_MODULE_PORT"], os.environ.get("MY_PORT", "-"), os.environ.get("MY_HOOK", "-")]).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", int(os.environ["NEXXUS_MODULE_PORT"])), H).serve_forever()
'''


def make_auto_module(ui, name, **manifest_extra):
    folder = ui / name
    folder.mkdir()
    (folder / "server.py").write_text(AUTO_MODULE)
    manifest = {"name": name, "type": "app", "hostnames": [f"{name}.localhost"], "port": "auto", "health": "/health",
                "start": {"cmd": ["{python}", "server.py"], "env": {"MY_PORT": "{port}"}}, "keep_running": True, **manifest_extra}
    (folder / "module.json").write_text(json.dumps(manifest))
    return folder


def wait_healthy(reg, name):
    for _ in range(80):
        if reg.sup.healthy(reg.cfg["modules"][name]):
            return True
        time.sleep(0.25)
    return False


def test_a_module_that_says_port_auto_gets_a_free_port_and_just_works(tmp_path):
    ui = tmp_path / "ui"; ui.mkdir()
    make_auto_module(ui, "robo", webhook_port="auto", webhook_paths=["/hook/"], start={"cmd": ["{python}", "server.py"], "env": {"MY_PORT": "{port}", "MY_HOOK": "{webhook_port}"}})
    folder, fixed = make_module(ui, "steady")                                     # a fixed-port module next to it
    reg = gateway.Registry(BASE, ui_dir=str(ui), min_interval=0, auto=gateway.AutoPorts(str(tmp_path / "auto.json")))
    assert reg.problems == []
    mod = reg.cfg["modules"]["robo"]
    lo, hi = gateway.AUTO_RANGE
    assert lo <= mod["port"] <= hi and lo <= mod["webhook_port"] <= hi and mod["port"] != mod["webhook_port"]
    assert reg.cfg["modules"]["steady"]["port"] == fixed                           # fixed ports are never touched
    try:
        reg.sup.keepalive()
        assert wait_healthy(reg, "robo")
        c = __import__("http.client").client.HTTPConnection("127.0.0.1", mod["port"], timeout=5); c.request("GET", "/x"); body = c.getresponse().read().decode()
        assert body == f"robo:{mod['port']}:{mod['port']}:{mod['webhook_port']}"      # {port} in env AND the standard NEXXUS_MODULE_* variables
    finally:
        reg.sup.stop("robo"); reg.sup.stop("steady")


def test_two_auto_modules_never_share_a_port_and_a_restart_keeps_them(tmp_path):
    ui = tmp_path / "ui"; ui.mkdir()
    make_auto_module(ui, "one"); make_auto_module(ui, "two")
    store = str(tmp_path / "auto.json")
    r1 = gateway.Registry(BASE, ui_dir=str(ui), min_interval=0, auto=gateway.AutoPorts(store))
    p1, p2 = r1.cfg["modules"]["one"]["port"], r1.cfg["modules"]["two"]["port"]
    assert p1 != p2
    r2 = gateway.Registry(BASE, ui_dir=str(ui), min_interval=0, auto=gateway.AutoPorts(store))      # "gateway restarted"
    assert (r2.cfg["modules"]["one"]["port"], r2.cfg["modules"]["two"]["port"]) == (p1, p2)


def test_auto_never_collides_with_a_fixed_port_module(tmp_path):
    ui = tmp_path / "ui"; ui.mkdir()
    store = gateway.AutoPorts(str(tmp_path / "auto.json"))
    probe = gateway.AutoPorts(str(tmp_path / "probe.json")).assign("clash", "port", set(), lambda p: False)       # where 'clash' would land
    make_module(ui, "squatter", port=probe)                                                                         # a fixed module sits exactly there
    make_auto_module(ui, "clash")
    reg = gateway.Registry(BASE, ui_dir=str(ui), min_interval=0, auto=store)
    assert reg.problems == [] and reg.cfg["modules"]["clash"]["port"] != probe and reg.cfg["modules"]["squatter"]["port"] == probe


def test_auto_without_a_port_store_is_reported_not_guessed(tmp_path):
    ui = tmp_path / "ui"; ui.mkdir()
    make_auto_module(ui, "robo")
    cfg, problems = gateway.discover(BASE, str(ui))
    assert "robo" not in cfg["modules"] and any("port store" in p for p in problems)


# ================================================================== 3. the private traffic log
def test_requests_are_logged_without_any_contents_or_secrets(gw):
    call(gw, "/api/x?token=SUPERSECRETVALUE&a=1", method="POST", body=b'{"password": "hunter2-body"}',
         headers={"Authorization": "Bearer abcdefghijklmnop123456", "Cookie": "sid=COOKIESECRET", "X-Nexxus-Admin-Token": "ADMINTOKENVALUE"})
    call(gw, "/files/" + "ab" * 30 + "/page")
    text = open(gw.bus, encoding="utf-8").read()
    for secret in ("SUPERSECRETVALUE", "hunter2-body", "abcdefghijklmnop123456", "COOKIESECRET", "ADMINTOKENVALUE", "ab" * 30):
        assert secret not in text
    rows = bus_lines(gw)
    req = next(r for r in rows if r["kind"] == "request" and r["path"].startswith("/api/x"))
    assert req["module"] == "nexxus" and req["method"] == "POST" and req["status"] == 200 and req["path"] == "/api/x?a&token"      # parameter NAMES only
    assert isinstance(req["ms"], int) and req["in"] > 0 and req["out"] == len("nexxus-bridge-ok") and req["outside"] is False
    assert any(r.get("path") == "/files/[id]/page" for r in rows)


def test_unknown_hosts_and_refused_outside_requests_are_recorded(gw):
    call(gw, "/", host="evil.example<script>")
    call(gw, "/api/mode", headers={"X-Forwarded-For": "6.6.6.6"})
    rows = bus_lines(gw)
    unk = next(r for r in rows if r["kind"] == "request" and r["module"] == "-")
    assert unk["status"] == 404 and "<" not in unk["host"] and ">" not in unk["host"]
    out = next(r for r in rows if r["kind"] == "request" and r["module"] == "nexxus" and r["status"] == 404)
    assert out["outside"] is True and any(r.get("what") == "bridge_refused_outside" for r in rows)


def test_the_log_rotates_instead_of_growing_forever(tmp_path):
    bus = gateway.BusLog(str(tmp_path / "b.jsonl")); bus.ROTATE = 300
    for i in range(40):
        bus.event("tick", n=i)
    assert os.path.exists(tmp_path / "b.jsonl.1") and os.path.getsize(tmp_path / "b.jsonl") < 2000


def test_a_registry_without_a_log_writes_nothing_anywhere(tmp_path):
    reg = gateway.Registry({"gateway": {"port": 0}, "reserved": {}, "modules": {}})
    srv = gateway.make_server({"gateway": {"host": "127.0.0.1", "port": 0}, "reserved": {}, "modules": {}}, registry=reg)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/", headers={"Host": "localhost"}), timeout=10).read()
    finally:
        srv.shutdown()
    assert reg.buslog.path is None


def test_starting_a_module_is_logged_as_an_event_not_its_output(tmp_path):
    ui = tmp_path / "ui"; ui.mkdir()
    make_auto_module(ui, "robo")
    bus = gateway.BusLog(str(tmp_path / "b.jsonl"))
    reg = gateway.Registry(BASE, ui_dir=str(ui), min_interval=0, auto=gateway.AutoPorts(str(tmp_path / "a.json")), buslog=bus)
    try:
        reg.sup.keepalive(); assert wait_healthy(reg, "robo")
    finally:
        reg.sup.stop("robo")
    rows = [json.loads(x) for x in open(tmp_path / "b.jsonl", encoding="utf-8").read().splitlines()]
    assert any(r.get("what") == "module_start" and r.get("module") == "robo" for r in rows) and any(r.get("what") == "module_stop" for r in rows)


def test_the_gateway_folder_itself_is_never_discovered_or_served(tmp_path):
    ui = tmp_path / "ui"; (ui / "_gateway").mkdir(parents=True)
    (ui / "_gateway" / "module.json").write_text(json.dumps({"name": "sneaky", "type": "app", "hostnames": ["s.localhost"], "port": 9999}))
    assert gateway.find_modules(str(ui)) == []
    assert os.path.dirname(gateway.BUS_LOG_PATH).endswith("logs") and gateway.BUS_LOG_PATH.startswith(gateway.HERE)
