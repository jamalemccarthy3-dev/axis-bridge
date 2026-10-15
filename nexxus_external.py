"""
nexxus_external.py - lets NEXXUS see and request utilities from INDEPENDENT modules over signed HTTP.

Why this exists: the 21 engines are closed silos that NEXXUS runs as subprocesses. A module like the blog or PICTHIS is a
separate program with its own server, data and secrets, so NEXXUS never runs its code and never imports it. Instead:

  * the module exposes one signed endpoint (POST /api/nexxus/rpc) declaring read-only utilities;
  * this file signs a request (HMAC-SHA256 + fresh timestamp, the same packet format as nexxus_governance.sign_command,
    but with a PER-MODULE secret, so a module never holds the NEXXUS-wide governance secret);
  * only JSON crosses the boundary, and only to modules on THIS computer (loopback addresses are enforced).

Configuration (read-only for NEXXUS; nothing else is read):
  external_modules.json   PUBLISHED by the module gateway (axis-ui-interface/_gateway), which scans the UI folder:
                          {"blog": {"base": "http://127.0.0.1:8080", "host": "blog.localhost:8080", "path": "...", "secret_file": "<abs path>"}}
                          Drop a module folder into axis-ui-interface and it appears; remove it and it disappears. Do not edit by hand.
  <module folder>/nexxus.secret   one line, 32+ characters, shared only with that module. NEXXUS reads ONLY the file named in the
                          published entry, and only if it is called nexxus.secret and is tiny; the value is used purely as a signing key.
  (or the environment variable NEXXUS_MODULE_SECRET_<NAME>)

mesh_bridge.py calls into this file from discover_utilities / call_utility / probe_engine / discover_all. If this file
is deleted, NEXXUS behaves exactly as before.
"""
import hashlib
import hmac
import http.client
import json
import os
import threading
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "external_modules.json"
LOOPBACK = ("127.0.0.1", "localhost")
MAX_REPLY = 1_000_000


def _load():
    try:
        roster = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    try:
        import vital_watch                                    # the read-only commercial watch: a watched folder is never callable, whatever the roster says
        for n in [k for k, m in roster.items() if isinstance(m, dict) and m.get("secret_file") and vital_watch.protected(Path(m["secret_file"]).parent)]:
            del roster[n]
    except ImportError:
        pass
    return roster


def names():
    return [n for n, m in _load().items() if isinstance(m, dict)]


def prune(UTILS):
    """Forget cached utilities of modules that were removed from the UI folder (called by NEXXUS before it lists utilities)."""
    live = set(names())
    for n in list(UTILS):
        if n not in live and UTILS[n].get("external"):
            del UTILS[n]


def is_external(name):
    return isinstance(_load().get(name), dict)


def _secret(name):
    s = os.environ.get("NEXXUS_MODULE_SECRET_" + name.upper().replace("-", "_"), "")
    if not s:
        m = _load().get(name) or {}
        try:
            f = Path(m.get("secret_file", "")).resolve()
            # only a file literally named nexxus.secret, small, and used only as a signing key (its content is never sent anywhere)
            if f.name == "nexxus.secret" and f.is_file() and f.stat().st_size <= 512:
                s = f.read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            s = ""
    return s.encode() if len(s) >= 32 else None


def _sign(packet, key):
    packet = dict(packet, origin="NEXXUS_EXECUTOR", ts=time.time())
    body = json.dumps({k: v for k, v in packet.items() if k != "signature"}, sort_keys=True).encode()
    packet["signature"] = hmac.new(key, body, hashlib.sha256).hexdigest()
    return packet


ACTIVITY_HOOK = None          # fn(name, op, ok) set by the server so the dashboard can light up when a module is called
TXN_HOOK = None               # fn(info dict) set by the server so AXIS LINK can record the call: when it was built, sent and answered, and what came back
BLOCK_CHECK = None            # fn(name) -> reason text when the perimeter has Hard Locked that module (nothing is then sent to it), else None
_TL = threading.local()


def _rpc(name, packet, timeout):
    _TL.t_sent, _TL.http = None, None
    t_start = time.time()
    blocked = None
    chk = BLOCK_CHECK
    if chk is not None:
        try:
            blocked = chk(name)
        except Exception:
            blocked = None
    if blocked:
        ok, out = False, "frozen: " + str(blocked)          # a Hard Lock on this module: nothing is sent to it
    else:
        ok, out = _rpc_inner(name, packet, timeout)
    t_end = time.time()
    hook = ACTIVITY_HOOK
    if hook is not None:
        try:
            hook(name, packet.get("op"), ok)
        except Exception:
            pass                  # a telemetry problem never changes the call's result
    thook = TXN_HOOK
    if thook is not None:
        try:
            thook({"name": name, "packet": packet, "ok": ok, "result": out if not ok else None, "error": None if ok else str(out)[:200], "t_start": t_start,
                   "t_sent": getattr(_TL, "t_sent", None), "t_end": t_end, "http": getattr(_TL, "http", None)})
        except Exception:
            pass
    return ok, out


def _rpc_inner(name, packet, timeout):
    """One signed request. Returns (ok, result_or_error_text). Never raises."""
    m = _load().get(name)
    if not isinstance(m, dict):
        return False, f"{name!r} is not a registered external module"
    base = urllib.parse.urlparse(m.get("base", ""))
    if base.scheme != "http" or base.hostname not in LOOPBACK:
        return False, "external modules must be on this computer (http://127.0.0.1 or localhost)"
    key = _secret(name)
    if not key:
        return False, f"no usable secret for {name} (its nexxus.secret file inside the UI folder)"
    try:
        conn = http.client.HTTPConnection(base.hostname, base.port or 80, timeout=timeout)
        conn.request("POST", m.get("path", "/api/nexxus/rpc"), json.dumps(_sign(packet, key)),
                     {"Content-Type": "application/json", "Host": m.get("host", base.netloc)})
        _TL.t_sent = time.time()
        resp = conn.getresponse()
        _TL.http = resp.status
        raw = resp.read(MAX_REPLY + 1)
        conn.close()
        if len(raw) > MAX_REPLY:
            return False, "module reply too large"
        data = json.loads(raw)
    except (OSError, ValueError, http.client.HTTPException) as e:
        return False, f"{type(e).__name__}: {e}"
    if resp.status != 200 or data.get("status") != "success":
        return False, str(data.get("error") or f"module answered HTTP {resp.status}")
    return True, data.get("result")


def discover(name, UTILS, timeout=15):
    ok, res = _rpc(name, {"op": "utilities"}, timeout)
    if not ok:
        return {"status": "error", "engine": name, "error": res}
    if not isinstance(res, dict):
        return {"status": "error", "engine": name, "error": "module returned an invalid utility list"}
    clean = {}
    for uname, d in res.items():
        d = d if isinstance(d, dict) else {}
        clean[str(uname)[:60]] = {"description": str(d.get("description", ""))[:300], "params": d.get("params") or {},
                                  "build": bool(d.get("build")), "chat_ok": bool(d.get("chat_ok"))}
    UTILS[name] = {"utilities": clean, "discovered_at": time.time(), "external": True}
    return {"status": "success", "engine": name, "utilities": clean}


def call(name, utility, args, timeout, allow_build, chat, UTILS, post_message):
    if name not in UTILS:
        d = discover(name, UTILS)
        if d["status"] != "success":
            return d
    decl = UTILS[name]["utilities"].get(utility)
    if decl is None:
        return {"status": "error", "engine": name, "error": f"{name} declares no utility {utility!r}"}
    if decl["build"] and not allow_build:
        return {"status": "error", "engine": name, "error": f"{utility!r} is a build utility: it runs only through the build process, not directly"}
    if chat and not decl["chat_ok"]:
        return {"status": "error", "engine": name, "error": f"{utility!r} is not enabled for chat; use the admin-token endpoint"}
    if args is not None and not isinstance(args, dict):
        return {"status": "error", "engine": name, "error": "args must be a JSON object"}
    t0 = time.time()
    ok, res = _rpc(name, {"op": "call", "utility": utility, "args": args or {}}, min(timeout, 60))
    out = {"status": "success", "engine": name, "utility": utility, "result": res} if ok else \
          {"status": "error", "engine": name, "utility": utility, "error": res}
    out["ms"] = round((time.time() - t0) * 1000, 1)
    try:
        post_message("nexxus", name, "utility_call", {"utility": utility, "outcome": out["status"]})
    except Exception:
        pass
    return out


def probe(name, deep=False, timeout=10):
    t0 = time.time()
    m = _load().get(name) or {}
    out = {"engine": name, "lane": name, "status": "found", "module": m.get("base"), "mesh_ready": True, "health": None, "error": None, "external": True}
    if deep:
        ok, res = _rpc(name, {"op": "health"}, timeout)
        if ok:
            out["health"] = res
        else:
            out["status"], out["error"] = "unhealthy", res
    out["probe_ms"] = round((time.time() - t0) * 1000, 2)
    return out
