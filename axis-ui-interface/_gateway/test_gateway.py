import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import gateway


def backend(name, seen):
    class H(BaseHTTPRequestHandler):
        def _go(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n).decode() if n else ""
            seen.append({"name": name, "path": self.path, "host": self.headers["Host"], "xff": self.headers.get("X-Forwarded-For"), "body": body})
            data = f"{name}:{self.path}".encode()
            self.send_response(200)
            self.send_header("Set-Cookie", f"a_{name}=1; Path=/")
            self.send_header("Set-Cookie", f"b_{name}=2; Path=/")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        do_GET = do_POST = _go
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def stack(tmp_path):
    seen = []
    blog, hooks, other = backend("blog", seen), backend("hooks", seen), backend("other", seen)
    site = tmp_path / "site"
    (site / "css").mkdir(parents=True)
    (site / "page.html").write_text("<h1>static page</h1>")
    (site / "css" / "a.css").write_text("body{}")
    (site / ".env").write_text("SECRET=1")
    (site / "notes.py").write_text("print(1)")
    cfg = {"gateway": {"host": "127.0.0.1", "port": 0}, "reserved": {"nexxus_bridge": 8000}, "modules": {
        "blog": {"type": "app", "hostnames": ["blog.localhost"], "port": blog.server_address[1], "webhook_port": hooks.server_address[1], "webhook_paths": ["/inbound/", "/stripe"]},
        "other": {"type": "app", "hostnames": ["other.localhost"], "port": other.server_address[1]},
        "site": {"type": "static", "hostnames": ["site.localhost"], "root": str(site), "index": "page.html", "files": ["page.html"], "prefixes": ["css/"]}}}
    assert gateway.validate(cfg) == []
    gw = gateway.make_server(cfg)
    threading.Thread(target=gw.serve_forever, daemon=True).start()
    yield type("S", (), {"url": f"http://127.0.0.1:{gw.server_address[1]}", "seen": seen, "blog": blog})
    for s in (gw, blog, hooks, other):
        s.shutdown()


def get(stack, path, host, method="GET", body=None, headers=None):
    req = urllib.request.Request(stack.url + path, data=body, method=method, headers={"Host": host, **(headers or {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), e.headers


def test_each_hostname_reaches_only_its_own_module(stack):
    assert get(stack, "/x", "blog.localhost")[1] == "blog:/x"
    assert get(stack, "/y", "other.localhost:8080")[1] == "other:/y"
    assert get(stack, "/", "evil.example.com")[0] == 404
    st, page, _ = get(stack, "/", "localhost")  # the bare host is the launcher page, never a module
    assert st == 200 and "Modules" in page and "blog:" not in page


def test_webhook_paths_go_to_the_webhook_port_only(stack):
    assert get(stack, "/inbound/secret", "blog.localhost", "POST", b"mail")[1] == "hooks:/inbound/secret"
    assert get(stack, "/stripe", "blog.localhost", "POST", b"{}")[1] == "hooks:/stripe"
    assert get(stack, "/stripe-fake", "blog.localhost")[1] == "blog:/stripe-fake"  # exact path only, not a prefix
    assert get(stack, "/inbound/x", "other.localhost")[1] == "other:/inbound/x"  # other modules have no webhook port


def test_request_bodies_and_repeated_cookies_pass_through(stack):
    st, body, headers = get(stack, "/api", "blog.localhost", "POST", b'{"a":1}', {"Content-Type": "application/json"})
    assert stack.seen[-1]["body"] == '{"a":1}'
    assert len(headers.get_all("Set-Cookie")) == 2


def test_client_cannot_forge_forwarding_headers(stack):
    get(stack, "/", "blog.localhost", headers={"X-Forwarded-For": "6.6.6.6", "X-Real-IP": "6.6.6.6"})
    assert stack.seen[-1]["xff"] == "127.0.0.1"


def test_a_down_module_returns_502_and_others_keep_working(stack):
    stack.blog.shutdown(); stack.blog.server_close()
    st, msg, _ = get(stack, "/", "blog.localhost")
    assert st == 502 and "blog" in msg
    assert get(stack, "/", "other.localhost")[0] == 200


def test_static_module_is_allow_list_only_and_traversal_proof(stack):
    assert get(stack, "/", "site.localhost")[1] == "<h1>static page</h1>"
    assert get(stack, "/css/a.css", "site.localhost")[0] == 200
    for bad in ("/.env", "/notes.py", "/../secret", "/%2e%2e/%2e%2e/windows/win.ini", "/css/../.env"):
        assert get(stack, bad, "site.localhost")[0] == 404, bad
    assert get(stack, "/", "site.localhost", "POST", b"x")[0] == 405


def test_config_validation_protects_the_bridge_port_and_catches_clashes():
    base = {"gateway": {"port": 8080}, "reserved": {"nexxus_bridge": 8000}, "modules": {}}
    bad = dict(base, modules={"a": {"type": "app", "hostnames": ["a.localhost"], "port": 8000},
                              "b": {"type": "app", "hostnames": ["a.localhost"], "port": 8701},
                              "c": {"type": "app", "hostnames": ["c.localhost"], "port": 8701, "webhook_port": 8080}})
    problems = " | ".join(gateway.validate(bad))
    assert "reserved for nexxus_bridge" in problems and "hostname a.localhost is used by both" in problems and "port 8701 is already used" in problems and "8080" in problems


def test_the_real_base_config_is_valid_and_never_routes_to_the_bridge_port():
    base = gateway.load_config()
    assert gateway.validate(base) == []
    cfg, problems = gateway.discover(base, gateway.UI_DIR)
    assert gateway.validate(cfg) == [] and all(m.get("port") != 8000 and m.get("webhook_port") != 8000 for m in cfg["modules"].values())



# ------------------------------------------------------------------ background modules: start, keep alive, wake, rest
import socket
import subprocess
import sys
import time

FAKE_MODULE = '''
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        d = ("ok:" + self.path).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
'''


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture
def managed(tmp_path):
    script = tmp_path / "fake_module.py"
    script.write_text(FAKE_MODULE)
    started = []

    def build(**extra):
        port = free_port()
        mod = {"type": "app", "hostnames": ["bg.localhost"], "port": port, "health": "/health", "wake_timeout": 15,
               "start": {"cwd": str(tmp_path), "cmd": ["{python}", str(script), str(port)]}, **extra}
        cfg = {"gateway": {"host": "127.0.0.1", "port": 0}, "reserved": {"nexxus_bridge": 8000}, "modules": {"bg": mod}}
        assert gateway.validate(cfg) == []
        clock = {"t": 1000.0}
        sup = gateway.Supervisor(cfg, clock=lambda: clock["t"])
        srv = gateway.make_server(cfg, sup)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append((srv, sup))
        return type("M", (), {"cfg": cfg, "sup": sup, "clock": clock, "port": port, "url": f"http://127.0.0.1:{srv.server_address[1]}"})
    yield build
    for srv, sup in started:
        sup.stop("bg"); srv.shutdown()


def fetch(m, path, host="bg.localhost", method="GET", headers=None):
    req = urllib.request.Request(m.url + path, method=method, headers={"Host": host, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_keep_running_module_is_started_once_and_restarted_if_it_dies(managed):
    m = managed(keep_running=True)
    assert not m.sup.healthy(m.cfg["modules"]["bg"])
    assert m.sup.keepalive() == ["bg"]
    for _ in range(60):
        if m.sup.healthy(m.cfg["modules"]["bg"]): break
        time.sleep(0.25)
    while m.sup.state["bg"].get("reviving"):                                    # let the first start finish bookkeeping
        time.sleep(0.05)
    assert m.sup.healthy(m.cfg["modules"]["bg"]) and m.sup.keepalive() == []   # healthy: nothing to do
    pid = m.sup.state["bg"]["proc"].pid
    m.sup.state["bg"]["proc"].kill(); m.sup.state["bg"]["proc"].wait()
    assert m.sup.keepalive() == ["bg"]                                          # died: brought back
    for _ in range(60):
        if m.sup.healthy(m.cfg["modules"]["bg"]): break
        time.sleep(0.25)
    assert m.sup.healthy(m.cfg["modules"]["bg"]) and m.sup.state["bg"]["proc"].pid != pid


def test_a_request_wakes_a_stopped_module_and_concurrent_requests_start_it_once(managed):
    m = managed()
    results = []
    threads = [threading.Thread(target=lambda: results.append(fetch(m, "/hello"))) for _ in range(5)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert all(r == (200, "ok:/hello") for r in results)
    assert m.sup.state["bg"]["owned"] is True


def test_modules_the_gateway_did_not_start_are_never_stopped(managed, tmp_path):
    m = managed(idle_minutes=1)
    outside = subprocess.Popen([sys.executable, str(tmp_path / "fake_module.py"), str(m.port)])   # started by someone else
    try:
        for _ in range(40):
            if m.sup.healthy(m.cfg["modules"]["bg"]): break
            time.sleep(0.25)
        assert fetch(m, "/x")[0] == 200
        m.clock["t"] += 99999
        assert m.sup.reap() == [] and m.sup.stop("bg") is False
        assert outside.poll() is None                                            # still running
    finally:
        outside.kill()


def test_only_idle_owned_modules_rest_and_never_with_requests_in_flight(managed):
    m = managed(idle_minutes=2)
    assert fetch(m, "/x")[0] == 200
    m.clock["t"] += 60
    assert m.sup.reap() == []                                                    # not idle long enough
    m.clock["t"] += 120
    m.sup.begin("bg")
    assert m.sup.reap() == []                                                    # a request is still in flight
    m.sup.end("bg"); m.clock["t"] += 200
    assert m.sup.reap() == ["bg"] and not m.sup.healthy(m.cfg["modules"]["bg"])
    assert fetch(m, "/again")[0] == 200                                          # and it wakes again on demand


def test_keep_running_modules_are_not_rested_and_survive_gateway_exit(managed):
    m = managed(keep_running=True)
    assert fetch(m, "/x")[0] == 200
    m.clock["t"] += 10 ** 6
    assert m.sup.reap() == []
    m.sup.shutdown()
    assert m.sup.healthy(m.cfg["modules"]["bg"])


def test_missing_folder_gives_a_clear_error_not_a_crash(managed):
    m = managed()
    m.cfg["modules"]["bg"]["start"]["cwd"] = "C:/definitely/not/here"
    st, msg = fetch(m, "/")
    assert st == 502 and "not found" in msg


def test_launcher_page_status_and_cross_site_protection(managed):
    m = managed(keep_running=True)
    assert fetch(m, "/", host="localhost:8080")[0] == 200 and "bg" in fetch(m, "/", host="localhost:8080")[1]
    status = json.loads(fetch(m, "/_status", host="127.0.0.1:8080")[1])["modules"]
    assert status[0]["name"] == "bg" and status[0]["keep_running"] is True
    assert fetch(m, "/_stop/bg", host="localhost:8080", method="POST", headers={"Origin": "http://evil.example.com"})[0] == 403
    assert fetch(m, "/_stop/nope", host="localhost:8080", method="POST")[0] == 404


def test_config_rules_for_background_modules():
    cfg = {"gateway": {"port": 8080}, "reserved": {}, "modules": {
        "a": {"type": "app", "hostnames": ["a.localhost"], "port": 8701, "keep_running": True},
        "b": {"type": "app", "hostnames": ["localhost"], "port": 8702, "idle_minutes": 5}}}
    problems = " | ".join(gateway.validate(cfg))
    assert "keep_running needs a start command" in problems and "idle_minutes needs a start command" in problems and "reserved for the launcher" in problems


def test_private_paths_are_local_only_and_never_reachable_through_a_proxy(tmp_path):
    seen = []
    blog = backend("blog", seen)
    cfg = {"gateway": {"host": "127.0.0.1", "port": 0}, "reserved": {"nexxus_bridge": 8000}, "modules": {
        "blog": {"type": "app", "hostnames": ["blog.localhost"], "port": blog.server_address[1], "private_paths": ["/api/nexxus/"]}}}
    gw = gateway.make_server(cfg)
    threading.Thread(target=gw.serve_forever, daemon=True).start()
    s = type("S", (), {"url": f"http://127.0.0.1:{gw.server_address[1]}", "seen": seen})
    try:
        assert get(s, "/api/nexxus/rpc", "blog.localhost", "POST", b"{}")[0] == 200                                    # same machine, no proxy headers
        for h in ({"X-Forwarded-For": "1.2.3.4"}, {"CF-Connecting-IP": "1.2.3.4"}, {"Forwarded": "for=1.2.3.4"}, {"X-Real-IP": "1.2.3.4"}):
            assert get(s, "/api/nexxus/rpc", "blog.localhost", "POST", b"{}", h)[0] == 404, h                           # came through a tunnel/proxy
        assert get(s, "/api/other", "blog.localhost", headers={"X-Forwarded-For": "1.2.3.4"})[0] == 200                # normal paths unaffected
    finally:
        gw.shutdown(); blog.shutdown()


# ------------------------------------------------------------------ drop-in / take-out discovery
import shutil

SECRET = "s" * 40


def make_module(ui, name, hostname=None, port=None, folder=None, script=True, secret=SECRET, **extra):
    folder = folder or (ui / name)
    folder.mkdir(parents=True, exist_ok=True)
    port = port or free_port()
    if script:
        (folder / "server.py").write_text(FAKE_MODULE)
    manifest = {"name": name, "type": "app", "hostnames": [hostname or f"{name}.localhost"], "port": port, "health": "/health",
                "start": {"cmd": ["{python}", "server.py", str(port)]}, "keep_running": True,
                "nexxus": {"path": "/api/nexxus/rpc", "secret_file": "nexxus.secret"}, **extra}
    (folder / "module.json").write_text(json.dumps(manifest))
    if secret is not None:
        (folder / "nexxus.secret").write_text(secret)
    return folder, port


BASE = {"gateway": {"host": "127.0.0.1", "port": 8080}, "reserved": {"nexxus_bridge": 8000}, "modules": {}}


@pytest.fixture
def ui(tmp_path):
    (tmp_path / "project-X").mkdir()               # a folder with no module.json: never touched
    (tmp_path / "config").mkdir()
    yield tmp_path


def registry(ui, base=None, **kw):
    return gateway.Registry(base or BASE, ui_dir=str(ui), publish_path=str(ui / "published.json"), min_interval=0, **kw)


def test_dropping_a_folder_in_adds_it_and_removing_it_takes_it_out_everywhere(ui):
    reg = registry(ui)
    assert reg.routes == {} and json.load(open(ui / "published.json")).keys() == {"_generated_by"}
    folder, port = make_module(ui, "demo")
    assert reg.reload() is True and "demo.localhost" in reg.routes
    pub = json.load(open(ui / "published.json"))
    assert pub["demo"]["host"] == "demo.localhost:8080" and pub["demo"]["secret_file"].endswith("nexxus.secret") and SECRET not in json.dumps(pub)
    reg.sup.keepalive()
    for _ in range(60):
        if reg.sup.healthy(reg.cfg["modules"]["demo"]): break
        time.sleep(0.25)
    assert reg.sup.healthy(reg.cfg["modules"]["demo"]) and reg.sup.state["demo"]["owned"]
    (folder / "module.json").unlink()                                           # "as simple as removing the file"
    assert reg.reload() is True and reg.routes == {} and "demo" not in json.load(open(ui / "published.json"))
    for _ in range(40):
        if not reg.sup.healthy({"port": port, "health": "/health"}): break
        time.sleep(0.25)
    assert not reg.sup.healthy({"port": port, "health": "/health"})             # the process the gateway started was stopped too
    shutil.rmtree(folder)                                                       # and now the folder itself is free to delete (Windows locks a folder while a program runs in it)


def test_a_registration_file_in_the_ui_root_points_at_a_module_elsewhere(ui, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("elsewhere") / "mymod"
    make_module(ui, "mymod", folder=elsewhere)
    (ui / "mymod.module.json").write_text(json.dumps({"folder": str(elsewhere)}))
    reg = registry(ui)
    assert "mymod.localhost" in reg.routes
    (ui / "mymod.module.json").unlink()                                          # remove the file: the module is gone, its folder is untouched
    reg.reload()
    assert reg.routes == {} and elsewhere.exists()


def test_one_bad_module_is_reported_and_skipped_without_hurting_the_good_ones(ui):
    make_module(ui, "good")
    (ui / "broken").mkdir(); (ui / "broken" / "module.json").write_text("{ not json")
    make_module(ui, "shelly", start={"cmd": ["cmd.exe", "/c", "calc"]})
    make_module(ui, "bridgey", port=8000)
    make_module(ui, "dupe", hostname="good.localhost")
    make_module(ui, "badname")
    (ui / "badname" / "module.json").write_text(json.dumps({"name": "Bad Name!", "hostnames": ["x.localhost"], "port": 8123}))
    (ui / "ptr.module.json").write_text(json.dumps({}))
    reg = registry(ui)
    assert list(reg.routes) == ["good.localhost"]
    text = " | ".join(reg.problems)
    for expect in ("module.json", "must be a list beginning with {python} or node", "reserved for nexxus_bridge", "hostname good.localhost is used by both", "name must be", "pointer file needs"):
        assert expect in text, expect


def test_manifests_cannot_reach_outside_their_own_folder(ui):
    make_module(ui, "esc1", start={"cwd": "../..", "cmd": ["{python}", "x.py"]})
    make_module(ui, "esc2")
    m = json.loads((ui / "esc2" / "module.json").read_text()); m["nexxus"]["secret_file"] = "../../../secret.txt"
    (ui / "esc2" / "module.json").write_text(json.dumps(m))
    make_module(ui, "esc3", type="static", root="../..", hostnames=["esc3.localhost"])
    reg = registry(ui)
    assert reg.routes == {} and sum("inside the module folder" in p for p in reg.problems) == 3


def test_a_module_without_a_usable_secret_still_runs_but_is_not_shown_to_nexxus(ui):
    make_module(ui, "nosecret", secret="short")
    reg = registry(ui)
    assert "nosecret.localhost" in reg.routes
    assert "nosecret" not in json.load(open(ui / "published.json")) and any("no usable secret" in p for p in reg.problems)


def test_a_real_folder_beats_a_leftover_pointer_with_the_same_name(ui, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("old") / "blog"
    make_module(ui, "blog", folder=elsewhere, hostname="old.localhost")
    (ui / "blog.module.json").write_text(json.dumps({"folder": str(elsewhere)}))
    make_module(ui, "blog", hostname="blog.localhost")                          # the module was moved into the UI folder
    reg = registry(ui)
    assert list(reg.routes) == ["blog.localhost"] and any("already registered" in p for p in reg.problems)


def test_a_new_module_is_picked_up_on_the_first_request_to_its_hostname(ui):
    quiet = dict(BASE, gateway={"host": "127.0.0.1", "port": 0})   # never the real 8080: on Windows a second listener on it would steal traffic
    reg = registry(ui, base=quiet)
    srv = gateway.make_server(quiet, registry=reg)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        def hit(host):
            try:
                with urllib.request.urlopen(urllib.request.Request(url + "/health", headers={"Host": host}), timeout=20) as r: return r.status
            except urllib.error.HTTPError as e: return e.code
        assert hit("fresh.localhost") == 404
        make_module(ui, "fresh")
        assert hit("fresh.localhost") == 200                                     # discovered, started and answered
    finally:
        reg.sup.shutdown(); reg.sup.stop("fresh"); srv.shutdown()
