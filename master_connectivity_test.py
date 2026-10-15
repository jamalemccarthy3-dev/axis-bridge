"""Tunnel (Tailscale) + Bluetooth controls. The tunnel is driven through a REAL executable (a fake `tailscale` that keeps state
in a file), so the subprocess path, argument lists, timeouts and parsing are exercised for real. Bluetooth uses a fake radio
on the real background event loop; the real bleak library / hardware are NOT available here.
Run: python3 test_connectivity.py"""
import asyncio, importlib.util, json, os, stat, sys, tempfile, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
tmp = Path(tempfile.mkdtemp(prefix="nx_conn_"))
os.environ.pop("NEXXUS_DEFAULT_MODE", None)
os.environ.update(NEXXUS_ADMIN_TOKEN="t", NEXXUS_DISABLE_AUTOSCHEDULER="1", NEXXUS_STAGING_DIR=str(tmp / "stg"), NEXXUS_VAULT_DIR=str(tmp / "vault"),
                  NEXXUS_PROBATION_PATH=str(tmp / "p.json"), NEXXUS_REVIEW_PATH=str(tmp / "r.json"), NEXXUS_CONTEXT_PATH=str(tmp / "h.json"),
                  NEXXUS_HUBMAP_PATH=str(tmp / "hm.json"), NEXXUS_DASHBOARDS_DIR=str(tmp / "dash"), NEXXUS_BT_PATH=str(tmp / "bt.json"),
                  NEXXUS_DISABLE_REVIEW_DAEMON="1", PYTHONPATH=str(HERE) + os.pathsep + os.environ.get("PYTHONPATH", ""))
sys.path.insert(0, str(HERE))
import tunnel_control as tc, bluetooth_control as bc
n = ok = 0
def chk(label, cond, extra=""):
    global n, ok; n += 1; ok += bool(cond); print("[%s] %s %s" % ("PASS" if cond else "FAIL", label, ("(" + str(extra)[:150] + ")") if extra else ""))

# ---------------- a fake `tailscale` executable with state in a file ----------------------------------------------------
STATE = tmp / "ts_state.json"
FAKE = tmp / "tailscale"
FAKE.write_text('''#!/usr/bin/env python3
import json, os, sys
S = os.environ["FAKE_TS_STATE"]
st = json.load(open(S))
a = sys.argv[1:]
log = open(S + ".log", "a"); log.write(json.dumps(a) + "\\n"); log.close()
def save(): json.dump(st, open(S, "w"))
if a[:2] == ["status", "--json"]:
    if st.get("garbage"): print("not json at all"); sys.exit(0)
    out = {"BackendState": st["state"], "AuthURL": st.get("auth", ""),
           "Self": {"HostName": "home-pc", "DNSName": "home-pc.tail1234.ts.net.", "TailscaleIPs": ["100.64.0.5"], "Online": st["state"] == "Running"},
           "Peer": {"k1": {"HostName": "phone", "OS": "iOS", "Online": True, "TailscaleIPs": ["100.64.0.9"]},
                    "k2": {"HostName": "laptop", "OS": "windows", "Online": False, "TailscaleIPs": ["100.64.0.7"]},
                    "k3": {"HostName": "alpha-tablet", "OS": "android", "Online": True, "TailscaleIPs": ["100.64.0.8"]}}}
    print(json.dumps(out)); sys.exit(0)
if a[:1] == ["up"]:
    if st.get("needs_login"):
        print("To authenticate, visit:\\n\\n\\thttps://login.tailscale.com/a/abc123def\\n"); sys.exit(1)
    st["state"] = "Running"; save(); sys.exit(0)
if a[:1] == ["down"]:
    st["state"] = "Stopped"; st["serve"] = False; save(); sys.exit(0)
if a[:2] == ["serve", "status"]:
    print("https://home-pc.tail1234.ts.net (tailnet only)\\n|-- / proxy http://127.0.0.1:8000" if st.get("serve") else "No serve config"); sys.exit(0)
if a[:2] == ["serve", "reset"]:
    st["serve"] = False; save(); sys.exit(0)
if a[:2] == ["serve", "--bg"]:
    if st.get("https_off"): sys.stderr.write("Serve is not enabled on your tailnet. HTTPS must be enabled first.\\n"); sys.exit(1)
    st["serve"] = True; save(); sys.exit(0)
sys.stderr.write("unexpected args %r\\n" % a); sys.exit(2)
''')
FAKE.chmod(FAKE.stat().st_mode | stat.S_IEXEC)
os.environ["FAKE_TS_STATE"] = str(STATE)
def setst(**k): STATE.write_text(json.dumps(k))
def calls(): return [json.loads(l) for l in (Path(str(STATE) + ".log").read_text().splitlines() if Path(str(STATE) + ".log").exists() else [])]

ctl = tc.TunnelController(exe=str(FAKE), port=8000)
setst(state="Stopped")
s0 = ctl.status()
chk("tunnel stopped: reported as STOPPED, not connected, not sharing", s0["state"] == "STOPPED" and not s0["connected"] and not s0["sharing"], s0["state"])
chk("peers listed with online devices first", [p["name"] for p in s0["peers"]] == ["alpha-tablet", "phone", "laptop"], [p["name"] for p in s0["peers"]])
chk("status tells you what to do next", "Connect" in s0["next_step"])
r = ctl.connect()
chk("connect: runs `tailscale up` and the PC really is Running afterwards", r["ok"] and r["status"]["connected"] and ["up", "--timeout=15s"] in calls(), calls()[-3:])
chk("this PC's tailnet address is reported", r["status"]["self"]["ips"] == ["100.64.0.5"] and r["status"]["self"]["dns"] == "home-pc.tail1234.ts.net")
chk("connected but not shared yet: says to press Share", not r["status"]["sharing"] and "Share" in r["status"]["next_step"])
r = ctl.share()
chk("share: `tailscale serve --bg 8000` and a real https address comes back", r["ok"] and r["status"]["sharing"] and r["status"]["url"] == "https://home-pc.tail1234.ts.net" and ["serve", "--bg", "8000"] in calls(), r.get("error"))
chk("sharing is detected from tailscale's own report, not remembered", ctl.status()["sharing"] is True)
r = ctl.unshare()
chk("stop sharing: dashboard no longer shared, PC still on the tailnet", r["ok"] and not r["status"]["sharing"] and r["status"]["connected"])
ctl.share(); r = ctl.disconnect()
chk("disconnect: leaves the tailnet AND clears sharing so nothing stays configured", r["ok"] and not r["status"]["connected"] and not r["status"]["sharing"] and ["serve", "reset"] in calls() and ["down"] in calls())
r = ctl.share()
chk("share while disconnected is refused with the reason", not r["ok"] and "Connect" in r["error"])
setst(state="Stopped", needs_login=True)
r = ctl.connect()
chk("first-time sign-in: the login link is returned and the result is not called ok", not r["ok"] and r["login_url"] == "https://login.tailscale.com/a/abc123def" and "Sign-in" in r["error"], r)
setst(state="Running", https_off=True)
r = ctl.share()
chk("share when HTTPS is not enabled on the tailnet: says exactly what to switch on", not r["ok"] and "HTTPS" in r["error"] and "admin console" in r["error"], r.get("error"))
setst(state="Running", garbage=True)
chk("garbage from the tailscale CLI is UNREACHABLE with a next step, not a crash", ctl.status()["state"] == "UNREACHABLE" and "Tailscale app" in ctl.status()["next_step"])
missing = tc.TunnelController(exe=None)
tc.find_tailscale, _old = (lambda: None), tc.find_tailscale
st = missing.status(); rc = missing.connect()
tc.find_tailscale = _old
chk("not installed: says so, with the install step; actions fail honestly", st["state"] == "NOT_INSTALLED" and "tailscale.com/download" in st["next_step"] and not rc["ok"] and "not installed" in rc["error"])
argvs = []
rec = tc.TunnelController(runner=lambda argv, timeout=0: (argvs.append(argv) or (0, "{}", "")), exe="/x/tailscale")
rec.status()
chk("commands are argument lists, never shell strings", all(isinstance(a, list) for a in argvs) and argvs[0][0] == "/x/tailscale", argvs)
to = tc.TunnelController(runner=lambda argv, timeout=0: (124, "", "timed out"), exe="/x/tailscale")
chk("a hung tailscale command times out into a clear state", to.status()["state"] == "UNREACHABLE" and not to.connect()["ok"])
os.environ["NEXXUS_TAILSCALE_EXE"] = str(FAKE); setst(state="Running")
chk("NEXXUS_TAILSCALE_EXE override is honoured", tc.find_tailscale() == str(FAKE))
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf): rc_cli = tc.main(["status"])
chk("CLI `status` against the fake: exit 0 and prints state, this PC and peers", rc_cli == 0 and "Tailscale: RUNNING" in buf.getvalue() and "home-pc.tail1234.ts.net" in buf.getvalue() and "alpha-tablet" in buf.getvalue(), buf.getvalue()[:120])
buf = io.StringIO()
with contextlib.redirect_stdout(buf): rc_cli = tc.main(["down"])
chk("CLI `down` disconnects", rc_cli == 0 and tc.TunnelController().status()["state"] == "STOPPED")
del os.environ["NEXXUS_TAILSCALE_EXE"]

# ---------------- Bluetooth with a fake radio on the real background loop ------------------------------------------------
class FakeRadio:
    name = "fake"
    def __init__(self): self.air = [{"address": "AA:BB:CC:DD:EE:01", "name": "Speaker", "rssi": -50}, {"address": "AA:BB:CC:DD:EE:02", "name": "Tracker", "rssi": -80},
                                    {"address": "AA:BB:CC:DD:EE:03", "name": "", "rssi": -90}]; self.up = set(); self.fail = None; self.threads = set(); self.scan_fail = False
    def available(self): return True, None
    async def scan(self, t):
        self.threads.add(threading.get_ident())
        if self.scan_fail: raise OSError("adapter is off")
        await asyncio.sleep(0.01); return list(self.air)
    async def connect(self, a, t):
        self.threads.add(threading.get_ident())
        if self.fail: raise TimeoutError(self.fail)
        self.up.add(a); return True
    async def disconnect(self, a):
        self.threads.add(threading.get_ident()); self.up.discard(a); return True
    def is_connected(self, a): return a in self.up
radio = FakeRadio(); bt = bc.BluetoothManager(radio, tmp / "btdev.json")
d = bt.scan(2)
chk("scan finds what is on the air; all three are 'discovered', none added or connected", [x["state"] for x in d["devices"]] == ["discovered"] * 3 and len(d["devices"]) == 3, d)
chk("an unnamed device is shown by its address", any(x["name"] == "AA:BB:CC:DD:EE:03" for x in d["devices"]))
chk("signal strength is carried through", {x["address"]: x["rssi"] for x in d["devices"]}["AA:BB:CC:DD:EE:01"] == -50)
bt.add("aa:bb:cc:dd:ee:01")
d = bt.devices()
chk("add: remembered under the name it advertised, state 'added', address normalised", d["devices"][0]["state"] == "added" and d["devices"][0]["name"] == "Speaker" and d["devices"][0]["address"] == "AA:BB:CC:DD:EE:01")
chk("adding twice does not duplicate", len(bc.BluetoothManager(radio, tmp / "btdev.json")._load()) == 1 and bt.add("AA:BB:CC:DD:EE:01")["address"] == "AA:BB:CC:DD:EE:01" and len(bt._load()) == 1)
chk("added devices survive a restart (file on disk)", [i["address"] for i in bc.BluetoothManager(radio, tmp / "btdev.json")._load()] == ["AA:BB:CC:DD:EE:01"])
v = bt.connect("AA:BB:CC:DD:EE:01")
chk("connect really opens the link and is only then reported 'connected'", v["state"] == "connected" and "AA:BB:CC:DD:EE:01" in radio.up)
chk("a connection stays up between separate calls (same background loop)", bt.devices()["devices"][0]["state"] == "connected" and len(radio.threads) == 1, radio.threads)
v = bt.disconnect("AA:BB:CC:DD:EE:01")
chk("disconnect really closes it; the device stays added", v["state"] == "added" and not radio.up)
e = None
try: bt.connect("AA:BB:CC:DD:EE:02")
except KeyError as x: e = x
chk("only devices you added can be connected", e is not None and not radio.up)
bt.add("AA:BB:CC:DD:EE:02", "My tracker"); radio.fail = "no response"
try: bt.connect("AA:BB:CC:DD:EE:02"); e = None
except RuntimeError as x: e = x
dv = {x["address"]: x for x in bt.devices()["devices"]}
chk("a failed connection says why and the device is NOT shown connected", e is not None and "no response" in str(e) and dv["AA:BB:CC:DD:EE:02"]["state"] == "added" and "no response" in dv["AA:BB:CC:DD:EE:02"]["error"])
radio.fail = None; bt.connect("AA:BB:CC:DD:EE:02"); bt.connect("AA:BB:CC:DD:EE:01")
chk("two devices can be connected at once", radio.up == {"AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"})
chk("disconnect_all closes every connection", sorted(bt.disconnect_all()) == ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"] and not radio.up)
bt.connect("AA:BB:CC:DD:EE:01"); bt.remove("AA:BB:CC:DD:EE:01")
chk("removing a connected device disconnects it first, then forgets it", not radio.up and "AA:BB:CC:DD:EE:01" not in [i["address"] for i in bt._load()])
try: bt.add("not-an-address"); e = None
except ValueError as x: e = x
chk("a bad address is refused with the expected format", e is not None and "AA:BB:CC" in str(e))
radio.air = [radio.air[1]]; d = bt.scan(2)
dv = {x["address"]: x for x in d["devices"]}
chk("a device that stopped advertising shows as not in range", dv["AA:BB:CC:DD:EE:02"]["in_range"] and "AA:BB:CC:DD:EE:01" not in dv)
radio.scan_fail = True
try: bt.scan(2); e = None
except RuntimeError as x: e = x
chk("a scan failure is explained (adapter off?) instead of showing an empty list", e is not None and "adapter is off" in str(e) and "switched on" in str(e))
radio.scan_fail = False
class Missing(FakeRadio):
    def available(self): return False, "bleak is not installed: run  pip install bleak"
mb = bc.BluetoothManager(Missing(), tmp / "b2.json")
try: mb.scan(2); e = None
except RuntimeError as x: e = x
chk("without the library the error says the exact install command", e is not None and "pip install bleak" in str(e) and mb.devices()["available"] is False)
real_ok, real_why = bc.BleakBackend.available()
chk("the REAL backend reports honestly whether bleak is installed here", real_ok or "pip install bleak" in real_why, real_why)
seen_t = []
_orig = radio.scan
async def _rec(t): seen_t.append(t); return await _orig(t)
radio.scan = _rec; bt.scan(999); bt.scan(0)
chk("scan time is clamped to 2-20 seconds", seen_t == [20.0, 2.0], seen_t)

# ---------------- routes ----------------------------------------------------------------------------------------------------
spec = importlib.util.spec_from_file_location("python_server_conn", str(HERE / "python_server.py"))
s = importlib.util.module_from_spec(spec); sys.modules["python_server_conn"] = s; spec.loader.exec_module(s)
c = s.app.test_client(); H = {"X-Nexxus-Admin-Token": "t"}
setst(state="Stopped"); s._tunnel = tc.TunnelController(exe=str(FAKE)); radio2 = FakeRadio(); s._bt = bc.BluetoothManager(radio2, tmp / "route_bt.json")
j = c.get("/api/tunnel/status").get_json()
chk("route: tunnel status is readable without a token", j["status"] == "success" and j["tunnel"]["state"] == "STOPPED")
chk("route: connect without the token is refused (and nothing ran)", c.post("/api/tunnel/connect").status_code == 401 and ["up", "--timeout=15s"] not in calls()[-1:])
chk("route: wrong token refused", c.post("/api/tunnel/connect", headers={"X-Nexxus-Admin-Token": "x"}).status_code == 401)
j = c.post("/api/tunnel/connect", headers=H).get_json()
chk("route: connect with the token joins the tailnet", j["status"] == "success" and j["result"]["status"]["connected"])
j = c.post("/api/tunnel/share", headers=H).get_json()
chk("route: share returns the https address", j["result"]["status"]["url"] == "https://home-pc.tail1234.ts.net")
j = c.post("/api/tunnel/disconnect", headers=H).get_json()
chk("route: disconnect works the same way (so you can cut it from anywhere you are connected)", j["status"] == "success" and not j["result"]["status"]["connected"])
chk("route: unknown tunnel action is a 404", c.post("/api/tunnel/format-disk", headers=H).status_code == 404)
setst(state="Stopped", needs_login=True)
r = c.post("/api/tunnel/connect", headers=H)
chk("route: a sign-in needed result is an error carrying the link", r.status_code == 409 and r.get_json()["result"]["login_url"].startswith("https://login.tailscale.com/"))
tok = os.environ.pop("NEXXUS_ADMIN_TOKEN")
chk("route: with no admin token configured these actions are switched off (503), not open", c.post("/api/tunnel/connect", headers=H).status_code == 503 and c.post("/api/bluetooth/scan", headers=H).status_code == 503)
os.environ["NEXXUS_ADMIN_TOKEN"] = tok
chk("route: bluetooth device list is readable (cached, never touches the radio)", c.get("/api/bluetooth/devices").get_json()["status"] == "success")
chk("route: scan needs the token", c.post("/api/bluetooth/scan", json={}).status_code == 401)
j = c.post("/api/bluetooth/scan", json={"seconds": 3}, headers=H).get_json()
chk("route: scan returns the devices heard", j["status"] == "success" and len(j["devices"]) == 3)
j = c.post("/api/bluetooth/add", json={"address": "AA:BB:CC:DD:EE:01"}, headers=H).get_json()
chk("route: add", [x["state"] for x in j["devices"]][0] == "added")
j = c.post("/api/bluetooth/connect", json={"address": "AA:BB:CC:DD:EE:01"}, headers=H).get_json()
chk("route: connect", j["devices"][0]["state"] == "connected")
j = c.post("/api/bluetooth/disconnect", json={"address": "AA:BB:CC:DD:EE:01"}, headers=H).get_json()
chk("route: disconnect", j["devices"][0]["state"] == "added")
r = c.post("/api/bluetooth/connect", json={"address": "AA:BB:CC:DD:EE:02"}, headers=H)
chk("route: connecting a device you never added is a 404 with the reason", r.status_code == 404 and "not in your added list" in r.get_json()["error"])
chk("route: malformed address is a 400", c.post("/api/bluetooth/add", json={"address": "zz"}, headers=H).status_code == 400)
radio2.fail = "out of range"
r = c.post("/api/bluetooth/add", json={"address": "AA:BB:CC:DD:EE:02"}, headers=H); r = c.post("/api/bluetooth/connect", json={"address": "AA:BB:CC:DD:EE:02"}, headers=H)
chk("route: a failed connect is a 409 carrying the reason and the real device list", r.status_code == 409 and "out of range" in r.get_json()["error"] and r.get_json()["devices"])
j = c.post("/api/bluetooth/remove", json={"address": "AA:BB:CC:DD:EE:02"}, headers=H).get_json()
chk("route: remove", "AA:BB:CC:DD:EE:02" not in [x["address"] for x in j["devices"] if x["added"]])
chk("route: unknown bluetooth action is a 404", c.post("/api/bluetooth/unpair-everything", headers=H).status_code == 404)

# ---------------- reachable through the tunnel ---------------------------------------------------------------------------------
with s.app.test_request_context("/", headers={"Host": "home-pc.tail1234.ts.net"}):
    chk("dashboards built through the tunnel embed an https address of that host (no mixed content)", s._dash_base() == "https://home-pc.tail1234.ts.net", s._dash_base())
with s.app.test_request_context("/", headers={"Host": "10.0.0.5:8000", "X-Forwarded-Proto": "https"}):
    chk("a forwarded https header is honoured", s._dash_base() == "https://10.0.0.5:8000")
with s.app.test_request_context("/", headers={"Host": "localhost:8000"}):
    chk("local use is unchanged (http://localhost:8000)", s._dash_base() == "http://localhost:8000")
with s.app.test_request_context("/", headers={"Host": "evil.com\"><script>", "X-Forwarded-Proto": "javascript"}):
    b = s._dash_base()
    chk("a hostile Host/proto header cannot inject script into generated pages", "<script>" not in __import__("dashboard_cycle")._safe_base(b) and __import__("dashboard_cycle")._safe_base(b) == "http://localhost:8000", b)
html = (HERE / "nexxus-fixed.html").read_text()
chk("the page talks to whichever address served it (works through the tunnel), localhost only as a file:// fallback",
    "location.origin" in html.split("const PYTHON_SERVER_BASE_URL")[1][:200] and "http://localhost:8000" in html.split("const PYTHON_SERVER_BASE_URL")[1][:250])

print("\n%d/%d passed" % (ok, n)); sys.exit(0 if ok == n else 1)