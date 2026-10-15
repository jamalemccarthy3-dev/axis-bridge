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

def _sign(packet):
    """Sign as THIS engine, with its own derived key, when the governance module supports it: the hub then knows the packet came from the engine it names, and engine A cannot sign as engine B.
    An older governance copy without sign_as_engine falls back to the shared-key signature (the hub still accepts that unless NEXXUS_REQUIRE_ENGINE_KEYS=1)."""
    try:
        from nexxus_governance import sign_as_engine
    except ImportError:
        from nexxus_governance import sign_command
        return sign_command(packet)
    return sign_as_engine(packet)


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