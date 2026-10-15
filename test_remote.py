"""test_remote.py - remote access over Tailscale and for phones: which addresses are bound and who is let in (net_bind), the heartbeat, the live event stream (hello, change events, heartbeat comments,
client cap), the host-side command queue (shared between devices, one device gets each item, retries do not double-queue), and the page wiring (link manager with stall watchdog and reconnect,
queue synced to the host, phone layout, touch controls in the generated 3D page). Real listeners on loopback addresses, real HTTP, throwaway token and folders. Run: python test_remote.py"""
import atexit
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

TMP = tempfile.mkdtemp(prefix="remote_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"), NEXXUS_BUS_LEDGER=os.path.join(TMP, "ledger.jsonl"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "creations"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"),
                  NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"), NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1",
                  NEXXUS_PUBLISH_DIR=os.path.join(TMP, "pub"), NEXXUS_FACTORY_DIR=os.path.join(TMP, "factory"), NEXXUS_DISPATCH_QUEUE=os.path.join(TMP, "dq.json"))
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, NEXUS)
import net_bind as NB  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
PAGE = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "render", "babylon_preview.html")


class Peers(unittest.TestCase):
    def test_only_this_machine_and_tailscale_are_let_in(self):
        for ok in ("127.0.0.1", "::1", "100.64.0.1", "100.116.81.71", "100.127.255.254", "fd7a:115c:a1e0::1", "::ffff:127.0.0.1", "::ffff:100.82.32.40"):
            self.assertTrue(NB.peer_allowed(ok, allow_lan=False), ok)
        for bad in ("8.8.8.8", "192.168.86.20", "10.1.2.3", "172.16.0.9", "100.128.0.1", "100.63.255.255", "169.254.1.1", "2001:db8::1", "", "not an ip", None):
            self.assertFalse(NB.peer_allowed(bad, allow_lan=False), bad)

    def test_the_lan_is_let_in_only_when_asked_for(self):
        self.assertTrue(NB.peer_allowed("192.168.86.20", allow_lan=True))
        self.assertTrue(NB.peer_allowed("10.1.2.3", allow_lan=True))
        self.assertFalse(NB.peer_allowed("8.8.8.8", allow_lan=True))
        self.assertFalse(NB.peer_allowed("169.254.1.1", allow_lan=True))


class Resolve(unittest.TestCase):
    def setUp(self):
        self._saved = NB._addrs
        import ipaddress
        NB._addrs = lambda: iter([("Ethernet", ipaddress.ip_address("192.168.86.235")), ("Tailscale", ipaddress.ip_address("100.116.81.71")), ("Loopback", ipaddress.ip_address("127.0.0.1"))])

    def tearDown(self):
        NB._addrs = self._saved

    def test_loopback_is_always_first_and_default(self):
        self.assertEqual(NB.resolve("")[0], ["127.0.0.1"])
        self.assertEqual(NB.resolve("loopback")[0], ["127.0.0.1"])

    def test_tailscale_finds_only_the_tailscale_range_and_never_the_lan(self):
        hosts, problems = NB.resolve("loopback,tailscale")
        self.assertEqual((hosts, problems), (["127.0.0.1", "100.116.81.71"], []))

    def test_lan_is_listed_only_if_asked_for(self):
        self.assertNotIn("192.168.86.235", NB.resolve("tailscale")[0])
        self.assertIn("192.168.86.235", NB.resolve("tailscale,lan")[0])

    def test_all_interfaces_and_strangers_are_refused_and_reported(self):
        for spec in ("0.0.0.0", "::", "8.8.8.8", "banana", "tailscale,0.0.0.0"):
            hosts, problems = NB.resolve(spec)
            self.assertNotIn("0.0.0.0", hosts)
            self.assertNotIn("8.8.8.8", hosts)
            if spec != "tailscale":
                self.assertTrue(problems or hosts == ["127.0.0.1", "100.116.81.71"], spec)
        self.assertTrue(NB.resolve("0.0.0.0")[1])
        self.assertTrue(NB.resolve("banana")[1])

    def test_no_tailscale_is_reported_not_fatal(self):
        import ipaddress
        NB._addrs = lambda: iter([("Loopback", ipaddress.ip_address("127.0.0.1"))])
        hosts, problems = NB.resolve("loopback,tailscale")
        self.assertEqual(hosts, ["127.0.0.1"])
        self.assertIn("no Tailscale address", problems[0])


class Listen(unittest.TestCase):
    """Real second listeners (127.0.0.2 and 127.0.0.3 are loopback addresses of this machine) serving a real Flask app."""

    @classmethod
    def setUpClass(cls):
        from flask import Flask
        cls.app = Flask("t")

        @cls.app.route("/ping")
        def ping():
            return "pong"
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()

    def get(self, host):
        return urllib.request.urlopen("http://%s:%d/ping" % (host, self.port), timeout=5).read()

    def test_an_extra_address_gets_its_own_listener(self):
        L = NB.Listeners(self.app, self.port, "127.0.0.2", log=lambda *a: None)
        L.sync()
        self.assertEqual(self.get("127.0.0.2"), b"pong")
        self.assertTrue(L.status()["listeners"]["127.0.0.2"]["ok"])
        self.assertEqual(L.problems, [])

    def test_a_port_conflict_on_one_address_is_reported_and_the_others_carry_on(self):
        blocker = socket.socket()
        blocker.bind(("127.0.0.3", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        try:
            L = NB.Listeners(self.app, port, "127.0.0.3,127.0.0.4", log=lambda *a: None)
            L.sync()
            st = L.status()["listeners"]
            self.assertFalse(st["127.0.0.3"]["ok"])
            self.assertIn("port", st["127.0.0.3"]["error"])
            self.assertTrue(st["127.0.0.4"]["ok"])
            self.assertEqual(urllib.request.urlopen("http://127.0.0.4:%d/ping" % port, timeout=5).read(), b"pong")
        finally:
            blocker.close()


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv
        import python_server as srv  # noqa: E402
        cls.http = srv.app.test_client()

    def test_strangers_get_403_and_tailscale_peers_are_served(self):
        for addr, code in (("8.8.8.8", 403), ("192.168.86.20", 403), ("100.82.32.40", 200), ("127.0.0.1", 200)):
            r = self.http.get("/api/ping", environ_overrides={"REMOTE_ADDR": addr})
            self.assertEqual(r.status_code, code, addr)
        self.assertIn("not allowed", self.http.get("/api/ping", environ_overrides={"REMOTE_ADDR": "8.8.8.8"}).get_json()["message"])
        os.environ["NEXXUS_ALLOW_LAN"] = "1"
        try:
            self.assertEqual(self.http.get("/api/ping", environ_overrides={"REMOTE_ADDR": "192.168.86.20"}).status_code, 200)
        finally:
            del os.environ["NEXXUS_ALLOW_LAN"]

    def test_ping_has_a_boot_id_that_is_stable_and_never_cached(self):
        a, b = self.http.get("/api/ping"), self.http.get("/api/ping")
        self.assertEqual(a.get_json()["boot"], b.get_json()["boot"])
        self.assertIn("no-store", a.headers["Cache-Control"])
        self.assertLess(abs(a.get_json()["t"] - time.time()), 5)

    def test_net_status_reports_the_listeners_and_who_you_are(self):
        d = self.http.get("/api/net/status", environ_overrides={"REMOTE_ADDR": "100.82.32.40"}).get_json()
        self.assertEqual((d["you"], d["listeners"]["127.0.0.1"]["ok"]), ("100.82.32.40", True))
        self.assertIn("tailscale_addresses", d)

    def post(self, path, body=None, admin=True, method="POST"):
        return self.http.open(path, method=method, json=body or {}, headers=ADMIN if admin else {})

    def test_the_host_queue_needs_the_token_and_is_shared(self):
        self.assertEqual(self.http.get("/api/dispatch-queue").status_code, 401)
        self.assertEqual(self.post("/api/dispatch-queue", {"text": "x"}, admin=False).status_code, 401)
        self.post("/api/dispatch-queue/clear")
        a = self.post("/api/dispatch-queue", {"id": "phone1", "text": "from the phone", "device": "phone"})
        b = self.post("/api/dispatch-queue", {"id": "pc1", "text": "from the computer", "device": "computer"})
        self.assertEqual((a.status_code, b.status_code), (201, 201))
        seen = self.http.get("/api/dispatch-queue", headers=ADMIN).get_json()
        self.assertEqual([i["text"] for i in seen["items"]], ["from the phone", "from the computer"])         # both devices see both
        self.assertEqual(seen["items"][0]["device"], "phone")

    def test_a_retry_after_a_dropped_connection_does_not_queue_twice(self):
        self.post("/api/dispatch-queue/clear")
        for _ in range(3):
            self.post("/api/dispatch-queue", {"id": "same", "text": "once only"})
        self.assertEqual(len(self.http.get("/api/dispatch-queue", headers=ADMIN).get_json()["items"]), 1)

    def test_exactly_one_device_gets_each_item(self):
        self.post("/api/dispatch-queue/clear")
        for i in range(10):
            self.post("/api/dispatch-queue", {"id": "i%d" % i, "text": "cmd %d" % i})
        got, lock = [], threading.Lock()

        def take():
            c = srv.app.test_client()
            while True:
                it = c.post("/api/dispatch-queue/next", json={}, headers=ADMIN).get_json()["item"]
                if it is None:
                    return
                with lock:
                    got.append(it["id"])
        ts = [threading.Thread(target=take) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(got), sorted("i%d" % i for i in range(10)))                                     # none lost, none twice
        self.assertEqual(self.http.get("/api/dispatch-queue", headers=ADMIN).get_json()["items"], [])

    def test_limits_and_errors(self):
        self.post("/api/dispatch-queue/clear")
        self.assertEqual(self.post("/api/dispatch-queue", {"text": "  "}).status_code, 400)
        self.assertEqual(self.post("/api/dispatch-queue", {"text": "x" * 4001}).status_code, 400)
        for i in range(50):
            self.assertEqual(self.post("/api/dispatch-queue", {"text": "c%d" % i}).status_code, 201)
        full = self.post("/api/dispatch-queue", {"text": "one too many"})
        self.assertEqual(full.status_code, 400)
        self.assertIn("full", full.get_json()["message"])
        self.assertEqual(self.post("/api/dispatch-queue/c0", method="DELETE").status_code, 200)
        self.assertEqual(self.post("/api/dispatch-queue/nope").status_code, 400)
        self.post("/api/dispatch-queue/clear")

    def test_the_queue_survives_a_restart(self):
        self.post("/api/dispatch-queue/clear")
        self.post("/api/dispatch-queue", {"id": "keep", "text": "still here"})
        self.assertEqual(json.load(open(os.environ["NEXXUS_DISPATCH_QUEUE"]))["items"][0]["text"], "still here")


class Stream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv
        import python_server as srv  # noqa: E402
        cls.http = srv.app.test_client()

    def chunks(self, resp, n, timeout=8):
        out, t0 = [], time.time()
        for c in resp.response:
            out.append(c.decode() if isinstance(c, bytes) else c)
            if len(out) >= n or time.time() - t0 > timeout:
                break
        return "".join(out)

    def test_hello_then_change_events_then_heartbeats(self):
        old = (srv._SSE_TICK, srv._SSE_HEARTBEAT)
        srv._SSE_TICK, srv._SSE_HEARTBEAT = 0.2, 0.6
        resp = self.http.get("/api/events", buffered=False)
        try:
            self.assertEqual(resp.mimetype, "text/event-stream")
            self.assertIn("no-cache", resp.headers["Cache-Control"])
            head = self.chunks(resp, 2)
            self.assertIn("retry: 3000", head)
            self.assertIn("event: hello", head)
            hello = json.loads(head.split("event: hello\ndata: ")[1].split("\n")[0])
            self.assertIn("dispatch_queue", hello["signals"])
            self.assertTrue(hello["boot"])
            self.http.post("/api/dispatch-queue", json={"id": "evt1", "text": "make an event"}, headers=ADMIN)
            body = self.chunks(resp, 3)
            self.assertIn("event: dispatch_queue", body)                                                       # a change on the host reaches every listening device
            self.assertNotIn("make an event", body)                                                            # counters only, never content
            beat = self.chunks(resp, 4)
            self.assertIn(": hb", beat)                                                                        # silence is never mistaken for a dead link
        finally:
            resp.close()
            srv._SSE_TICK, srv._SSE_HEARTBEAT = old
            self.http.post("/api/dispatch-queue/clear", json={}, headers=ADMIN)

    def test_closing_releases_the_slot_and_the_cap_is_enforced(self):
        base = srv._sse["clients"]
        srv._SSE_MAX_CLIENTS, old = base + 1, srv._SSE_MAX_CLIENTS
        try:
            a = self.http.get("/api/events", buffered=False)
            self.chunks(a, 1)
            self.assertEqual(srv._sse["clients"], base + 1)
            self.assertEqual(self.http.get("/api/events").status_code, 429)                                    # one too many
            a.close()
            deadline = time.time() + 5
            while srv._sse["clients"] != base and time.time() < deadline:
                time.sleep(0.1)
            self.assertEqual(srv._sse["clients"], base)
            b = self.http.get("/api/events", buffered=False)
            self.assertEqual(b.status_code, 200)
            b.close()
        finally:
            srv._SSE_MAX_CLIENTS = old

    def test_strangers_cannot_open_the_stream(self):
        self.assertEqual(self.http.get("/api/events", environ_overrides={"REMOTE_ADDR": "8.8.8.8"}).status_code, 403)


class PageSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = open(PAGE, encoding="utf-8").read()

    def test_the_link_manager_has_heartbeat_watchdog_backoff_and_resync(self):
        h = self.html
        for needle in ("new EventSource(PYTHON_SERVER_BASE_URL + '/api/events')", "'/api/ping'", "Date.now() - nxl.lastMsg > 25000", "Math.min(30000, 1000 * Math.pow(2,", "window.addEventListener('online'",
                       "visibilitychange", "navigator.connection.addEventListener('change'", "nxl.boot !== d.boot", "function nxlResync", "Offline. Your commands are kept"):
            self.assertIn(needle, h, needle)
        for name in ("notifications", "creations", "input_queue", "dispatch_queue", "tools_log"):
            self.assertIn("on('%s'" % name, h, name)

    def test_the_queue_goes_to_the_host_and_falls_back_to_the_device(self):
        h = self.html
        for needle in ("api/dispatch-queue", "api/dispatch-queue/next", "local: true", "on the host: shared with your other devices", "on this device only", "dspSync()"):
            self.assertIn(needle, h, needle)

    def test_the_page_never_hardcodes_the_hosts_address(self):
        self.assertIn("(location.protocol === 'http:' || location.protocol === 'https:') ? location.origin", self.html)
        self.assertIn("settingsEndpoint.innerText = PYTHON_SERVER_BASE_URL", self.html)

    def test_the_phone_layout_is_loaded_last_and_covers_the_touch_basics(self):
        h = self.html
        self.assertGreater(h.index('id="nxMobile"'), h.index(".fx-panel {"))
        block = h.split('id="nxMobile"')[1].split("</style>")[0]
        for needle in ("@media (max-width: 820px)", ".left-sidebar", "nxm-open", "font-size: 16px", "min-height: 44px", "env(safe-area-inset-bottom)", "orientation: landscape", "right: -110vw !important"):
            self.assertIn(needle, block, needle)
        self.assertIn("function nxmInit", h)
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1.0"', h)

    def test_generated_3d_pages_have_touch_controls(self):
        import factory_env
        js = factory_env._ENV_JS
        for needle in ("pointerType === 'mouse'", "pointerdown", "setPointerCapture", "touch.jump", "tstick", "left thumb walks"):
            self.assertTrue(needle in js or needle in open(os.path.join(ROOT, "factory_env.py"), encoding="utf-8").read(), needle)
        self.assertNotIn("touchstart", js.replace("'ontouchstart' in window", ""))                                  # pointer events only: one path for mouse, touch and pen


if __name__ == "__main__":
    unittest.main(verbosity=1)
