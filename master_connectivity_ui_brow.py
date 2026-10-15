"""Real Chromium + real Flask server test of the Connections panel (tunnel + Bluetooth) in nexxus-fixed.html.
The tunnel is a fake `tailscale` executable (state in a file); Bluetooth is a fake radio. Real Tailscale / real hardware are NOT used.
Run: python3 test_connectivity_ui_browser.py"""
import asyncio, importlib.util, json, os, socket, stat, sys, tempfile, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
PORT = 8000
_run = _ok = 0
def check(label, cond, extra=""):
    global _run, _ok
    _run += 1; _ok += bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f"  ({str(extra)[:140]})" if extra else ""))

FAKE_TS = '''#!/usr/bin/env python3
import json, os, sys
S = os.environ["FAKE_TS_STATE"]; st = json.load(open(S)); a = sys.argv[1:]
def save(): json.dump(st, open(S, "w"))
if a[:2] == ["status", "--json"]:
    print(json.dumps({"BackendState": st["state"], "AuthURL": "",
      "Self": {"HostName": "home-pc", "DNSName": "home-pc.tail1234.ts.net.", "TailscaleIPs": ["100.64.0.5"], "Online": st["state"] == "Running"},
      "Peer": {"k1": {"HostName": "phone", "OS": "iOS", "Online": True, "TailscaleIPs": ["100.64.0.9"]}}})); sys.exit(0)
if a[:1] == ["up"]: st["state"] = "Running"; save(); sys.exit(0)
if a[:1] == ["down"]: st["state"] = "Stopped"; st["serve"] = False; save(); sys.exit(0)
if a[:2] == ["serve", "status"]: print("https://home-pc.tail1234.ts.net\\n|-- / proxy http://127.0.0.1:8000" if st.get("serve") else "No serve config"); sys.exit(0)
if a[:2] == ["serve", "reset"]: st["serve"] = False; save(); sys.exit(0)
if a[:2] == ["serve", "--bg"]: st["serve"] = True; save(); sys.exit(0)
sys.exit(2)
'''
class Radio:
    name = "fake"
    def __init__(self): self.up = set()
    def available(self): return True, None
    async def scan(self, t): await asyncio.sleep(0.01); return [{"address": "AA:BB:CC:DD:EE:01", "name": "Speaker", "rssi": -50}]
    async def connect(self, a, t): self.up.add(a); return True
    async def disconnect(self, a): self.up.discard(a); return True
    def is_connected(self, a): return a in self.up

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed"); return
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            print("SKIP: port busy"); return
    except OSError: pass
    tmp = Path(tempfile.mkdtemp(prefix="nx_conn_ui_"))
    state = tmp / "ts.json"; state.write_text(json.dumps({"state": "Stopped"}))
    fake = tmp / "tailscale"; fake.write_text(FAKE_TS); fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    os.environ.pop("NEXXUS_DEFAULT_MODE", None)
    os.environ.update({"FAKE_TS_STATE": str(state), "NEXXUS_ADMIN_TOKEN": "t", "NEXXUS_DISABLE_AUTOSCHEDULER": "1", "NEXXUS_STAGING_DIR": str(tmp / "stg"),
        "NEXXUS_VAULT_DIR": str(tmp / "vault"), "NEXXUS_PROBATION_PATH": str(tmp / "p.json"), "NEXXUS_REVIEW_PATH": str(tmp / "r.json"),
        "NEXXUS_CONTEXT_PATH": str(tmp / "h.json"), "NEXXUS_HUBMAP_PATH": str(tmp / "hm.json"), "NEXXUS_DASHBOARDS_DIR": str(tmp / "dash"),
        "NEXXUS_BT_PATH": str(tmp / "bt.json"), "NEXXUS_DISABLE_REVIEW_DAEMON": "1", "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")})
    sys.path.insert(0, str(ROOT))
    import tunnel_control as tc, bluetooth_control as bc
    spec = importlib.util.spec_from_file_location("python_server_conn_ui", str(ROOT / "python_server.py"))
    server = importlib.util.module_from_spec(spec); sys.modules["python_server_conn_ui"] = server; spec.loader.exec_module(server)
    radio = Radio()
    server._tunnel = tc.TunnelController(exe=str(fake)); server._bt = bc.BluetoothManager(radio, tmp / "dev.json")
    threading.Thread(target=lambda: server.app.run(host="127.0.0.1", port=PORT, threaded=True, debug=False, use_reloader=False), daemon=True).start()
    for _ in range(100):
        try: socket.create_connection(("127.0.0.1", PORT), timeout=0.3).close(); break
        except OSError: time.sleep(0.1)
    errors, prompts = [], []
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if Path(exe).exists() else pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_context(viewport={"width": 1600, "height": 1300}).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: (prompts.append(d.message), d.accept("t")))
        page.goto((ROOT / "nexxus-fixed.html").as_uri())
        page.wait_for_function("document.getElementById('tunnelState') && document.getElementById('tunnelState').dataset.state", timeout=20000)
        click = lambda sel: page.locator(sel).dispatch_event("click")
        def wait_state(s): page.wait_for_function("document.getElementById('tunnelState').dataset.state === '%s'" % s, timeout=15000)
        print("===== tunnel =====")
        check("panel shows the real state (Stopped) with Connect on and Disconnect off", "STOPPED" in page.inner_text("#tunnelState") and not page.is_disabled("#tunnelConnectBtn") and page.is_disabled("#tunnelDisconnectBtn"))
        check("it says what to do next", "Connect" in page.inner_text("#tunnelNext"))
        click("#tunnelConnectBtn"); wait_state("RUNNING")
        check("Connect asked for the admin token and joined the tailnet", any("Admin token" in p for p in prompts) and json.loads(state.read_text())["state"] == "Running")
        check("peers and this PC are listed", "phone (online)" in page.inner_text("#tunnelInfo") and "home-pc" in page.inner_text("#tunnelInfo"))
        check("Share is now available, Connect is not", not page.is_disabled("#tunnelShareBtn") and page.is_disabled("#tunnelConnectBtn"))
        click("#tunnelShareBtn"); page.wait_for_function("document.getElementById('tunnelInfo').innerText.includes('https://home-pc.tail1234.ts.net')", timeout=15000)
        check("Share shows the https address for your other devices", json.loads(state.read_text()).get("serve") is True)
        n = len(prompts); click("#tunnelUnshareBtn"); page.wait_for_function("!document.getElementById('tunnelInfo').innerText.includes('Open on your other')", timeout=15000)
        check("Stop sharing removes the address and the token is remembered (no second prompt)", json.loads(state.read_text()).get("serve") is False and len(prompts) == n)
        click("#tunnelDisconnectBtn"); wait_state("STOPPED")
        check("Disconnect really leaves the tailnet", json.loads(state.read_text())["state"] == "Stopped" and not page.is_disabled("#tunnelConnectBtn"))
        print("===== bluetooth =====")
        check("empty list tells you to scan", "Scan" in page.inner_text("#btList"))
        click("#btScanBtn"); page.wait_for_selector('[data-bt-addr="AA:BB:CC:DD:EE:01"]', timeout=15000)
        row = page.locator('[data-bt-addr="AA:BB:CC:DD:EE:01"]')
        check("scan lists the device it heard as discovered, with Add", "Speaker" in row.inner_text() and "discovered" in row.inner_text() and row.locator("button", has_text="Add").count() == 1)
        row.locator("button", has_text="Add").dispatch_event("click"); page.wait_for_function("document.querySelector('[data-bt-addr] .hm-chip').innerText.startsWith('added')", timeout=10000)
        check("Add remembers it (file on disk)", json.loads((tmp / "dev.json").read_text())[0]["address"] == "AA:BB:CC:DD:EE:01")
        page.locator('[data-bt-addr] button', has_text="Connect").dispatch_event("click"); page.wait_for_function("document.querySelector('[data-bt-addr] .hm-chip').innerText === 'connected'", timeout=15000)
        check("Connect really opened the link", "AA:BB:CC:DD:EE:01" in radio.up)
        page.locator('[data-bt-addr] button', has_text="Disconnect").dispatch_event("click"); page.wait_for_function("document.querySelector('[data-bt-addr] .hm-chip').innerText.startsWith('added')", timeout=15000)
        check("Disconnect really closed it", not radio.up)
        page.fill("#btAddr", "11:22:33:44:55:66"); click("#btAddBtn"); page.wait_for_selector('[data-bt-addr="11:22:33:44:55:66"]', timeout=10000)
        check("a device can be added by address too", True)
        page.locator('[data-bt-addr="11:22:33:44:55:66"] button', has_text="×").dispatch_event("click")
        page.wait_for_function("!document.querySelector('[data-bt-addr=\"11:22:33:44:55:66\"]')", timeout=10000)
        check("Remove forgets it", "11:22:33:44:55:66" not in (tmp / "dev.json").read_text())
        print("===== wrong token / unavailable =====")
        page.evaluate("recon.adminToken = 'wrong'"); page.once("dialog", lambda d: d.accept("wrong"))
        click("#tunnelConnectBtn"); page.wait_for_function("document.getElementById('tunnelNext').innerText.startsWith('Not done')", timeout=10000)
        check("a wrong token is reported, not hidden, and nothing ran", "unauthorized" in page.inner_text("#tunnelNext").lower() and json.loads(state.read_text())["state"] == "Stopped", page.inner_text("#tunnelNext"))
        check("no page errors", errors == [], errors)
        browser.close()
    print(f"\n{_ok}/{_run} passed"); sys.exit(0 if _ok == _run else 1)
if __name__ == "__main__": main()