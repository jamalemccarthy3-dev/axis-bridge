"""net_bind.py - which network addresses the dashboard listens on, and who may talk to it.

The server always listens on loopback (127.0.0.1). NEXXUS_BIND adds more, as a comma list:
    loopback           127.0.0.1 (always on, listed for clarity)
    tailscale          every address this machine has in Tailscale's range (100.64.0.0/10), found from the network interfaces; rechecked every 20 s, so a tunnel that comes up after the
                       server starts (or comes back after a reconnect) gets its listener without a restart
    lan                private-network addresses (192.168.x.x, 10.x.x.x, 172.16-31.x.x): off unless you list it, because it exposes the dashboard to everything on that Wi-Fi
    <an IP address>    that exact address, if this machine owns it
There is no "all interfaces" (0.0.0.0) option. Each address gets its own listener on the same port (distinct addresses do not conflict); a listener that cannot bind (the port is taken on that
address) is reported and the others carry on.

peer_allowed() is the second lock: even if something reached a listener, only loopback and Tailscale peers (and private-LAN peers if NEXXUS_ALLOW_LAN=1) are served; everything else gets a 403.
Changes to data still need the admin token, which this module never sees.
"""
import ipaddress
import os
import threading
import time

CGNAT = ipaddress.ip_network("100.64.0.0/10")
TS6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
WATCH_EVERY = 20


def _addrs():
    try:
        import psutil
        import socket
        for nic, lst in psutil.net_if_addrs().items():
            for a in lst:
                if a.family == socket.AF_INET:
                    yield nic, ipaddress.ip_address(a.address)
    except Exception:
        return


def tailscale_addresses():
    return [str(ip) for _, ip in _addrs() if ip in CGNAT]


def lan_addresses():
    return [str(ip) for _, ip in _addrs() if ip.is_private and not ip.is_loopback and not ip.is_link_local and ip not in CGNAT]


def owned(ip):
    return any(str(a) == ip for _, a in _addrs())


def resolve(spec):
    """-> ([hosts to listen on, loopback first], [problems]). Unknown or unowned entries are reported, never silently dropped."""
    hosts, problems = ["127.0.0.1"], []
    for tok in [t.strip().lower() for t in str(spec or "loopback").split(",") if t.strip()]:
        if tok == "loopback":
            continue
        elif tok == "tailscale":
            found = tailscale_addresses()
            if not found:
                problems.append("tailscale: no Tailscale address on this machine right now (is Tailscale running and connected?); it will be picked up when it appears")
            hosts += found
        elif tok == "lan":
            hosts += lan_addresses()
        else:
            try:
                ip = ipaddress.ip_address(tok)
            except ValueError:
                problems.append("%r is not loopback, tailscale, lan or an IP address" % tok)
                continue
            if ip.is_unspecified:
                problems.append("0.0.0.0 / :: (all interfaces) is not allowed; list the addresses you want")
            elif not owned(tok) and not ip.is_loopback:
                problems.append("%s is not an address of this machine" % tok)
            else:
                hosts.append(tok)
    seen, out = set(), []
    for h in hosts:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out, problems


def is_loopback(addr):
    try:
        ip = ipaddress.ip_address(str(addr).split("%")[0])
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_loopback


def peer_allowed(addr, allow_lan=None):
    try:
        ip = ipaddress.ip_address(str(addr).split("%")[0])
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    if ip.is_loopback or ip in CGNAT or ip in TS6:
        return True
    if allow_lan is None:
        allow_lan = os.environ.get("NEXXUS_ALLOW_LAN") == "1"
    return bool(allow_lan and ip.is_private and not ip.is_link_local)


class Listeners:
    """The extra listeners (loopback is served by the main thread). start() binds what resolve() found; the watcher adds addresses that appear later."""

    def __init__(self, app, port, spec, log=print):
        self.app, self.port, self.spec, self.log = app, int(port), spec, log
        self.state = {}                      # host -> {"ok": bool, "error": str|None, "since": ts}
        self.problems = []
        self._servers, self._lock, self._stop = {}, threading.Lock(), threading.Event()

    def _bind(self, host):
        from werkzeug.serving import make_server
        import socket
        err = None
        probe = socket.socket()                                    # find out first: werkzeug answers a failed bind with sys.exit(), which must never stop the server
        try:
            probe.bind((host, self.port))
        except OSError as e:
            err = e
        finally:
            probe.close()
        srv = None
        if err is None:
            try:
                srv = make_server(host, self.port, self.app, threaded=True)
            except (OSError, SystemExit) as e:
                err = e
        if srv is None:
            self.state[host] = {"ok": False, "error": "%s (is the port already used on that address?)" % (err if isinstance(err, OSError) else "could not bind"), "since": time.time()}
            self.log("[NET] cannot listen on %s:%d: %s" % (host, self.port, err))
            return
        threading.Thread(target=srv.serve_forever, daemon=True, name="listen-%s" % host).start()
        self._servers[host] = srv
        self.state[host] = {"ok": True, "error": None, "since": time.time()}
        self.log("[NET] listening on http://%s:%d/" % (host, self.port))

    def sync(self):
        hosts, self.problems = resolve(self.spec)
        with self._lock:
            for h in hosts:
                if h == "127.0.0.1" or (h in self._servers):
                    continue
                self._bind(h)

    def start(self):
        self.sync()
        if "tailscale" in str(self.spec).lower() or "lan" in str(self.spec).lower():
            threading.Thread(target=self._watch, daemon=True, name="listen-watch").start()
        return self

    def _watch(self):
        while not self._stop.wait(WATCH_EVERY):
            try:
                self.sync()
            except Exception as e:
                self.log("[NET] address check failed: %s" % e)

    def status(self):
        return {"spec": self.spec, "port": self.port, "listeners": dict(self.state, **{"127.0.0.1": {"ok": True, "error": None, "since": None}}), "problems": list(self.problems),
                "tailscale_addresses": tailscale_addresses(), "allow_lan": os.environ.get("NEXXUS_ALLOW_LAN") == "1"}
