# =====================================================================
# NEXXUS GOVERNANCE SNIPPET  (only for engines that need to SPEAK FIRST)
# Lets this engine send signed messages to NEXXUS, or to another engine
# through the hub (alerts, results, requests).
# Paste it ABOVE the MESH snippet in the engine's entry file. It does NOT
# replace the mesh snippet - an engine uses the mesh snippet, and adds this
# one only if it needs to send messages.
#
# Needs, in the engine's environment:
#   * nexxus_governance.py importable (copy it next to this engine, or put
#     its folder on PYTHONPATH)
#   * NEXXUS_GOVERNANCE_SECRET set - the same value the server uses
#   * optional NEXXUS_MESH_URL (default http://127.0.0.1:8000)
# Set ENGINE_NAME to this engine's exact mesh name.
# =====================================================================
import json, os, urllib.request

ENGINE_NAME = "axis-port"   # <-- CHANGE: this engine's name, e.g. "axis-validator"

def _sign(packet):
    """Sign as THIS engine, with its own derived key, when the governance module supports it: the hub then knows the packet came from the engine it names, and engine A cannot sign as engine B.
    An older governance copy without sign_as_engine falls back to the shared-key signature (the hub still accepts that unless NEXXUS_REQUIRE_ENGINE_KEYS=1)."""
    try:
        from nexxus_governance import sign_as_engine
    except ImportError:
        from nexxus_governance import sign_command
        return sign_command(packet)
    return sign_as_engine(packet)


def send_to_nexxus(kind, body, to="nexxus"):
    """Send a signed message. to='nexxus' (inbox) or another engine name (relayed
    by the hub). Returns the hub's reply dict, or {'status':'error',...} - never raises."""
    try:
        from nexxus_governance import sign_command
        packet = _sign({"engine": ENGINE_NAME, "to": to, "kind": kind, "body": body})
        req = urllib.request.Request(
            os.environ.get("NEXXUS_MESH_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/mesh/message",
            data=json.dumps(packet).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}

PEERS = {"version": None, "peers": []}   # the engine's copy of the mesh map (who is live, what they offer)

def get_peers():
    """Fetch the mesh map from NEXXUS (the other engines, whether each is live, and their utilities).
    Also tells the hub which map version this engine now knows. Returns the map, or {'status':'error'}."""
    try:
        from nexxus_governance import sign_command
        packet = _sign({"engine": ENGINE_NAME})
        req = urllib.request.Request(
            os.environ.get("NEXXUS_MESH_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/mesh/peers",
            data=json.dumps(packet).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            m = json.loads(r.read().decode("utf-8"))
        if m.get("status") == "success":
            PEERS["version"], PEERS["peers"] = m["version"], m["peers"]
        return m
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}

# Use anywhere in the engine, e.g.:
#   send_to_nexxus("alert", {"msg": "disk low"})
#   send_to_nexxus("request", {"instruction": "ping"}, to="axis-link")
#   get_peers()   # PEERS["peers"] now lists every engine, live or not, and the utilities it offers

# =====================================================================
# LIVE STATUS SNIPPET  (for engines that run continuously)
# Makes the engine report in to NEXXUS every few seconds with a signed
# heartbeat: its state, its own memory/CPU, and any numbers you choose. The
# dashboard then shows it as LIVE - and flips it to NO HEARTBEAT on its own
# if the engine stops reporting (crash, hang, closed window).
#
# ORDER in the engine's entry file (top to bottom):
#   1. NEXXUS GOVERNANCE snippet   (defines ENGINE_NAME - set it there)
#   2. this LIVE STATUS snippet
#   3. MESH snippet
#   4. the engine's own code, which calls start_heartbeat() once at startup
#
# Needs the same things as the governance snippet: nexxus_governance.py importable,
# NEXXUS_GOVERNANCE_SECRET set, optional NEXXUS_MESH_URL. psutil is optional
# (without it the engine still reports state, just not memory/CPU).
# =====================================================================
import json, os, threading, time, urllib.request

_hb_state = {"state": "running", "extra": {}}

def set_status(state=None, **metrics):
    """Update what the next heartbeat says, e.g. set_status("processing", queue_depth=12)."""
    if state is not None:
        _hb_state["state"] = state
    _hb_state["extra"].update(metrics)

def _own_metrics():
    m = {}
    try:
        import psutil
        p = psutil.Process()
        m["rss_mb"] = round(p.memory_info().rss / 1048576, 1)
        m["cpu_percent"] = p.cpu_percent(interval=None)
        m["threads"] = p.num_threads()
    except Exception:
        pass
    m["pid"] = os.getpid()
    return m

def send_heartbeat(interval=10):
    """One heartbeat now. Returns the hub's reply, or {'status':'error',...}. Never raises."""
    try:
        from nexxus_governance import sign_command
        packet = _sign({"engine": ENGINE_NAME, "state": _hb_state["state"], "interval": interval,
                               "metrics": {**_own_metrics(), **_hb_state["extra"]}})
        req = urllib.request.Request(
            os.environ.get("NEXXUS_MESH_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/mesh/status",
            data=json.dumps(packet).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            reply = json.loads(r.read().decode("utf-8"))
        # Awareness: the hub tells us the current mesh-map version. If it changed, re-fetch the map
        # (needs the governance snippet's get_peers) so this engine always knows who else is live.
        v = reply.get("mesh_version")
        if v is not None and v != _hb_state.get("map_version") and "get_peers" in globals():
            if get_peers().get("status") == "success":
                _hb_state["map_version"] = v
        return reply
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}

def start_heartbeat(interval=10):
    """Call once when the engine starts. Beats from a background thread (it dies with the engine)."""
    def _loop():
        while True:
            send_heartbeat(interval)
            time.sleep(interval)
    t = threading.Thread(target=_loop, daemon=True, name="nexxus-heartbeat")
    t.start()
    return t

# =====================================================================
# MESH SNIPPET  (paste into EVERY engine)
# Lets NEXXUS health-check this engine, give it instructions, send it MESSAGES, and ASK IT TO
# RUN ITS UTILITIES (the jobs this engine knows how to do).
# Paste at the BOTTOM of the engine's *_core.py, ABOVE the engine's own
# startup code (the mesh runs this file with --mesh and expects it to
# answer and exit). If you also use the GOVERNANCE and LIVE STATUS snippets,
# those go ABOVE this one.
#
# What it answers (instruction):   health | health_detail | status | ping | message | inbox | anything else -> "unknown instruction"
#   * health         {"ok": true} only if the checks below pass; otherwise {"ok": false, "checks": {...}, "error": "<plain words>"}. The checks test what this engine depends on:
#                    its own file parses, it can sign a packet (governance module + secret), the hub answers. It fails safely and says why.
#   * message        the engine RECEIVES it: stored in the inbox, then handed to YOUR hook if you defined one. Define, ABOVE this snippet:
#                        def on_message(sender, payload): ...        # return any JSON value; it comes back as "reply"
#                    If your hook raises, the message is still received (ok:false, received:true, error: the reason) and the engine keeps running.
#   * inbox          the newest 100 messages, oldest first. Kept on disk as <this file>.inbox.json (or NEXXUS_ENGINE_INBOX), because the hub starts a fresh
#                    process for every call: a list in memory would be gone when the call ends.
#   * ping           {"ok": true, ...}: proves the handler is reachable.
# Needs nothing else: no extra files, no secrets (health uses the governance snippet's signing if it is present).
# =====================================================================
# MESH_PROTOCOL = 1
import sys, json, os, time

MESH_UTILITIES = {}

def utility(name=None, description="", params=None, build=False, chat_ok=False):
    """Register a function as a utility NEXXUS can request. Use as a decorator:

        @utility("summarize", "Summarize a text file", params={"path": "str"}, chat_ok=True)
        def summarize(path): ...        # called with the args NEXXUS sends; return any JSON value

    build=True   -> only ever runs through the build process (a job + NEXXUS's truth gate).
    chat_ok=True -> may be started from the NEXXUS chat box (otherwise it needs the admin token).
    Raise an exception (or return {"status": "error", ...}) to report failure honestly."""
    def deco(fn):
        MESH_UTILITIES[name or fn.__name__] = {"fn": fn, "description": description, "params": params or {},
                                               "build": build, "chat_ok": chat_ok}
        return fn
    return deco

def _engine_name():
    return globals().get("ENGINE_NAME") or "engine"

def _scrub(text):
    """Plain words only: no file paths, no keys or long tokens, never the signing secret, in anything this engine says."""
    import re
    t = str(text)
    sec = os.environ.get("NEXXUS_GOVERNANCE_SECRET", "")
    if len(sec) >= 8:
        t = t.replace(sec, "<redacted>")
    t = re.sub(r"[A-Za-z]:[\\/][^\s'\"<>|]+", "<path>", t)
    t = re.sub(r"(?<![\w.])/(?:[\w.-]+/)+[\w.-]*", "<path>", t)
    t = re.sub(r"\b[A-Za-z0-9_\-]{32,}\b", "<redacted>", t)
    return t[:300]

# ---- messages and the inbox ----------------------------------------------------------------------
_INBOX_MAX = 100
_INBOX_ITEM_BYTES = 8192

def _inbox_path():
    """The inbox belongs to THIS engine file: <this file>.inbox.json (NEXXUS_ENGINE_INBOX overrides). Per file, not per folder or name, so two engines can never read each other's messages."""
    p = os.environ.get("NEXXUS_ENGINE_INBOX")
    if p:
        return p
    try:
        return os.path.abspath(__file__) + ".inbox.json"
    except NameError:                           # run without a file (a test that exec()s this snippet): use the temp folder
        import tempfile
        safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in _engine_name())[:60]
        return os.path.join(tempfile.gettempdir(), "nexxus_inbox_%s.json" % safe)

def _inbox_read():
    try:
        with open(_inbox_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []

def _inbox_add(entry):
    """Append and keep the newest 100. Written atomically; if two calls land in the same instant the later write wins. Returns whether it was saved."""
    try:
        items = (_inbox_read() + [entry])[-_INBOX_MAX:]
        path = _inbox_path()
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f)
        os.replace(tmp, path)
        return True
    except OSError:
        return False

def _handle_message(payload):
    payload = payload if isinstance(payload, dict) else {}
    sender = str(payload.get("from") or "unknown")[:60]
    try:
        stored = payload if len(json.dumps(payload)) <= _INBOX_ITEM_BYTES else {"from": sender, "truncated": True}
    except (TypeError, ValueError):
        stored = {"from": sender, "unreadable": True}
    now = time.time()
    saved = _inbox_add({"from": sender, "payload": stored, "ts": now})
    out = {"ok": True, "received": True, "engine": _engine_name(), "from": sender, "ts": now, "inbox_saved": saved}
    hook = globals().get("on_message")
    if callable(hook):
        try:
            out["reply"] = hook(sender, payload)
        except Exception as e:                  # the engine's own code failed: say so, keep the engine alive, and the message still counts as received
            out["ok"] = False
            out["error"] = _scrub("%s: %s" % (type(e).__name__, e))
    return out

# ---- health: measured, not assumed ---------------------------------------------------------------
def _health_checks():
    """-> (checks, info). checks decide ok; info is extra detail. A one-shot probe (--mesh) has no heartbeat thread of its own, so liveness is judged by the hub's view of the engine."""
    checks, info = {}, {}
    try:
        import ast as _ast
        with open(os.path.abspath(__file__), "r", encoding="utf-8") as _f:
            _ast.parse(_f.read())
        checks["entry_file_parses"] = True
    except NameError:
        pass                                    # no file to check (exec'd snippet)
    except Exception as e:
        checks["entry_file_parses"] = False
        info["entry_file_error"] = type(e).__name__
    try:
        from nexxus_governance import sign_command
        _sign = globals().get("_sign")
        _sign({"engine": _engine_name(), "probe": "health"}) if _sign else sign_command({"engine": _engine_name(), "probe": "health"})
        checks["can_sign_packets"] = True
    except Exception as e:
        checks["can_sign_packets"] = False
        info["sign_error"] = type(e).__name__
    try:
        import urllib.request
        # 127.0.0.1, not "localhost": on Windows a "localhost" connection waited ~2 s here (measured 2030 ms vs 4 ms)
        _url = os.environ.get("NEXXUS_MESH_URL", "http://127.0.0.1:8000").rstrip("/").replace("//localhost", "//127.0.0.1") + "/api/ping"
        with urllib.request.urlopen(_url, timeout=3) as _r:
            checks["hub_reachable"] = (_r.status == 200)
    except Exception as e:
        checks["hub_reachable"] = False
        info["hub_error"] = type(e).__name__
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        _probe = os.path.join(here, ".health_probe.tmp")
        with open(_probe, "w") as _f:
            _f.write("ok")
        os.remove(_probe)
        info["folder_writable"] = True
        import shutil
        info["disk_free_gb"] = round(shutil.disk_usage(here).free / 1e9, 1)
    except Exception:
        info["folder_writable"] = False
    om = globals().get("_own_metrics")
    if om:
        try:
            info.update(om())
        except Exception:
            pass
    return checks, info

_FRIENDLY = {"entry_file_parses": "this engine's own file does not parse",
             "can_sign_packets": "it cannot sign packets (the signing secret or the governance module is missing)",
             "hub_reachable": "it cannot reach the NEXXUS hub"}

def _real_health():
    checks, _info = _health_checks()
    if all(checks.values()):
        return {"ok": True}
    return {"ok": False, "engine": _engine_name(), "checks": checks, "error": "; ".join(_FRIENDLY.get(k, k) for k, v in checks.items() if not v)}

def _health_detail():
    checks, info = _health_checks()
    return {"ok": all(checks.values()), "engine": _engine_name(), "checks": checks, "info": info}

def mesh_handle(op, instruction, payload):
    """Instructions & health. op is 'health' or 'instruct'. Return any JSON-able value."""
    if op == "health":
        return _real_health()
    if instruction == "health_detail":
        return _health_detail()
    if instruction == "status":
        try:
            hb = globals()["_hb_state"]
            return {"state": hb["state"], **globals()["_own_metrics"](), **hb["extra"]}
        except Exception:
            return {"state": "unknown"}
    if instruction == "ping":
        return {"ok": True, "engine": _engine_name(), "ts": time.time()}
    if instruction == "message":
        return _handle_message(payload)
    if instruction == "inbox":
        items = _inbox_read()[-_INBOX_MAX:]
        return {"ok": True, "engine": _engine_name(), "count": len(items), "messages": items}
    return {"error": f"unknown instruction {instruction!r}"}

def _mesh_dispatch(req):
    op = req.get("op")
    if op == "utilities":
        return {n: {k: v for k, v in d.items() if k != "fn"} for n, d in MESH_UTILITIES.items()}
    if op == "call":
        d = MESH_UTILITIES.get(req.get("utility"))
        if d is None:
            return {"status": "error", "error": f"no utility {req.get('utility')!r}"}
        try:
            out = d["fn"](**(req.get("args") or {}))
        except Exception as e:
            return {"status": "error", "error": _scrub(f"{type(e).__name__}: {e}")}
        # A utility may report its own failure by returning {"status": "error"}; otherwise it succeeded.
        if isinstance(out, dict) and out.get("status") == "error":
            return out
        return {"status": "success", "output": out}
    return mesh_handle(op, req.get("instruction"), req.get("payload") or {})

if "--mesh" in sys.argv:
    _req = json.loads(sys.stdin.read() or "{}")
    print(json.dumps({"result": _mesh_dispatch(_req)}))
    sys.exit(0)
# ---- engine's normal startup code continues below this line ----

# ---- your engine's own code goes here. Start the heartbeat once, at startup: ----
if __name__ == "__main__":
    start_heartbeat()
    while True:          # keep the process alive; the heartbeat thread is a daemon
        time.sleep(3600)
