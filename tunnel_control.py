"""
tunnel_control.py - connect / disconnect / check the Tailscale tunnel from NEXXUS (Windows, macOS, Linux).

Why Tailscale: a private network between YOUR devices. Your phone or laptop, wherever you are, reaches the PC that
runs NEXXUS without opening any port on your router and without a public address.

Two separate things, kept separate on purpose:
  CONNECT / DISCONNECT   the PC joins or leaves your tailnet  (`tailscale up` / `tailscale down`).
                         Disconnected = no remote device can reach this PC at all.
  SHARE / STOP SHARING   `tailscale serve` forwards https://<this-pc>.<tailnet>.ts.net to the NEXXUS server, which
                         stays bound to 127.0.0.1. Stop sharing = the dashboard is no longer reachable remotely,
                         while the PC stays on your tailnet.

Nothing here touches the network itself: it drives the `tailscale` command line and reports exactly what that said.
Every command is a list (never a shell string), has a timeout, and its output is returned, not guessed at.

CLI:  python tunnel_control.py status | up | down | share | unshare   [--json]
"""
import json
import os
import shutil
import subprocess
import sys

DEFAULT_PORT = 8000
TIMEOUT = 25
WIN_PATHS = [r"C:\Program Files\Tailscale\tailscale.exe", r"C:\Program Files (x86)\Tailscale\tailscale.exe"]


def find_tailscale():
    env = os.environ.get("NEXXUS_TAILSCALE_EXE")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("tailscale")
    if found:
        return found
    for p in WIN_PATHS:
        if os.path.isfile(p):
            return p
    return None


def _default_runner(argv, timeout=TIMEOUT):
    """-> (returncode, stdout, stderr). Never raises."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, shell=False)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired as e:
        def _text(x):
            return x.decode("utf-8", "replace") if isinstance(x, (bytes, bytearray)) else (x or "")
        # keep what the command printed before it hung: it is usually the reason (a login link, "Serve is not enabled...")
        return 124, _text(e.stdout), _text(e.stderr) + "timed out after %ds (a first-time `tailscale up` waits for you to log in)" % timeout
    except OSError as e:
        return 127, "", "%s: %s" % (type(e).__name__, e)


class TunnelController:
    def __init__(self, runner=None, exe=None, port=DEFAULT_PORT):
        self._run = runner or _default_runner
        self._exe = exe
        self.port = port

    # ---- plumbing
    def _tailscale(self, *args, timeout=TIMEOUT):
        exe = self._exe or find_tailscale()
        if not exe:
            return 127, "", "tailscale is not installed (or not on PATH)"
        return self._run([exe] + list(args), timeout)

    @staticmethod
    def _login_url(text):
        for tok in str(text).split():
            if tok.startswith("https://login.tailscale.com/") or tok.startswith("https://") and "tailscale" in tok:
                return tok.strip()
        return None

    # ---- read
    def status(self):
        """Real state from `tailscale status --json` and `tailscale serve status`."""
        exe = self._exe or find_tailscale()
        out = {"installed": bool(exe), "exe": exe, "state": "NOT_INSTALLED", "connected": False, "sharing": False,
               "self": None, "peers": [], "url": None, "login_url": None, "error": None, "port": self.port,
               "next_step": "Install Tailscale (free personal plan) from tailscale.com/download, sign in, then press Refresh."}
        if not exe:
            return out
        rc, so, se = self._tailscale("status", "--json")
        try:
            j = json.loads(so) if so.strip() else {}
        except ValueError:
            j = {}
        if not j:
            out.update(state="UNREACHABLE", error=(se or so or "tailscale returned nothing").strip()[:300],
                       next_step="Start the Tailscale app (system tray) and press Refresh.")
            return out
        state = j.get("BackendState") or "Unknown"
        me = j.get("Self") or {}
        out["state"] = state.upper()
        out["connected"] = state == "Running"
        out["login_url"] = j.get("AuthURL") or None
        dns = str(me.get("DNSName") or "").rstrip(".")
        out["self"] = {"name": me.get("HostName"), "dns": dns or None, "ips": me.get("TailscaleIPs") or [], "online": bool(me.get("Online"))}
        peers = []
        for p in (j.get("Peer") or {}).values():
            peers.append({"name": p.get("HostName"), "os": p.get("OS"), "online": bool(p.get("Online")), "ips": p.get("TailscaleIPs") or [],
                          "last_seen": p.get("LastSeen")})
        out["peers"] = sorted(peers, key=lambda x: (not x["online"], str(x["name"]).lower()))
        if out["connected"]:
            rc2, so2, se2 = self._tailscale("serve", "status")
            text = (so2 or "") + (se2 or "")
            out["sharing"] = rc2 == 0 and ("127.0.0.1:%d" % self.port in text or "localhost:%d" % self.port in text)
            out["serve_text"] = text.strip()[:400]
            if out["sharing"] and dns:
                out["url"] = "https://%s" % dns
        out["next_step"] = (
            "Press Connect, then sign in in the browser window if asked." if state in ("Stopped", "NoState") else
            "Open the sign-in link, log in, then press Refresh." if state == "NeedsLogin" else
            ("Connected and shared: open %s on any device signed into your tailnet." % out["url"]) if out["sharing"] else
            "Connected. Press Share to make the dashboard reachable from your other devices." if out["connected"] else
            "State is %s; check the Tailscale app." % state)
        return out

    # ---- act
    def _result(self, what, rc, so, se):
        text = ((so or "") + "\n" + (se or "")).strip()
        res = {"action": what, "ok": rc == 0, "output": text[:500], "login_url": self._login_url(text)}
        if rc != 0 and not res["login_url"]:
            res["error"] = text[:300] or "exit code %s" % rc
        res["status"] = self.status()
        return res

    def connect(self):
        # --timeout lets a first-time login print its link instead of waiting forever
        rc, so, se = self._tailscale("up", "--timeout=15s", timeout=30)
        r = self._result("connect", rc, so, se)
        if r["login_url"]:
            r["ok"] = False
            r["error"] = "Sign-in needed: open the link, log in, then press Connect again."
        return r

    def disconnect(self):
        """Leave the tailnet. Also stops sharing first, so nothing stays configured."""
        self._tailscale("serve", "reset")
        rc, so, se = self._tailscale("down")
        return self._result("disconnect", rc, so, se)

    def share(self):
        st = self.status()
        if not st["connected"]:
            return {"action": "share", "ok": False, "error": "Not connected: press Connect first.", "status": st}
        rc, so, se = self._tailscale("serve", "--bg", str(self.port))
        r = self._result("share", rc, so, se)
        out = so + "\n" + se
        if "serve is not enabled" in out.lower():
            link = self._login_url(out)
            r["ok"] = False
            r["action_url"] = link
            r["error"] = ("Tailscale Serve is not switched on for your tailnet yet. Open this link once while signed in to Tailscale and approve it, then press Share again: %s" % (link or "(see the Tailscale admin console)"))
            return r
        if rc != 0 and "https" in (so + se).lower():
            r["error"] = "HTTPS is not enabled for your tailnet yet: in the Tailscale admin console (DNS page) turn on HTTPS certificates once, then press Share again."
        return r

    def unshare(self):
        rc, so, se = self._tailscale("serve", "reset")
        return self._result("unshare", rc, so, se)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    cmd = argv[0] if argv else "status"
    tc = TunnelController()
    fn = {"status": tc.status, "up": tc.connect, "down": tc.disconnect, "share": tc.share, "unshare": tc.unshare}.get(cmd)
    if not fn:
        print(__doc__); return 2
    res = fn()
    if as_json:
        print(json.dumps(res, indent=2)); return 0
    st = res.get("status", res)
    if "action" in res:
        print(("OK: " if res["ok"] else "FAILED: ") + res["action"] + ((" - " + res["error"]) if res.get("error") else ""))
        if res.get("login_url"): print("Sign in here:", res["login_url"])
    print("Tailscale: %s%s" % (st["state"], " (shared at %s)" % st["url"] if st.get("url") else ""))
    if st.get("self"): print("This PC: %s  %s" % (st["self"]["dns"] or st["self"]["name"], ", ".join(st["self"]["ips"])))
    for p in st["peers"]: print("  %-22s %-8s %s" % (p["name"], "online" if p["online"] else "offline", p["os"] or ""))
    print(st["next_step"])
    return 0 if st["installed"] else 1


if __name__ == "__main__":
    sys.exit(main())