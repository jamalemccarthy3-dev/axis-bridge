"""telemetry_hub.py - the master desktop side of sandbox telemetry: pull, validate, store, summarise.

Users' sandbox pages (the public PWA) send opt-in, anonymous events to a small relay you control (relay/worker.js). This desktop NEVER accepts connections from the internet: it calls out to the
relay, fetches the queued events, checks every one against the same fixed schema the relay and the page use (the relay is not trusted), stores the valid ones and tells the relay to delete them.

What an event can contain (anything else is dropped): e event name from EVENTS, t unix seconds, v client version, i random install id, s standalone 0/1, w screen class s/m/l, x short tag.
No text, no IP address, no user agent, no names. The relay URL and pull key come from NEXXUS_RELAY_URL and NEXXUS_RELAY_KEY (never committed).

Command line: python telemetry_hub.py pull | summary
"""
import collections
import json
import os
import re
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "nexxus_data", "telemetry")
STORE_PATH = os.path.join(STORE_DIR, "sandbox_events.jsonl")
EVENTS = ("page_view", "install_clicked", "app_installed", "section_opened", "feedback_opened", "review_link_clicked", "error")
FIELDS = {"e", "t", "v", "i", "s", "w", "x"}
_ID = re.compile(r"^[0-9a-f]{32}$")
_TAG = re.compile(r"^[a-z0-9_-]{1,32}$")
_VER = re.compile(r"^[0-9a-z.\-]{1,16}$")
MAX_STORED = 200_000          # events kept; the oldest are trimmed
_LOCK = threading.RLock()


def validate(ev, now=None):
    """-> the cleaned event dict, or None if it does not fit the schema exactly."""
    now = time.time() if now is None else now
    if not isinstance(ev, dict) or not set(ev) <= FIELDS or not {"e", "t", "i"} <= set(ev):
        return None
    if ev["e"] not in EVENTS or not isinstance(ev["i"], str) or not _ID.match(ev["i"]):
        return None
    t = ev["t"]
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not (now - 90 * 86400 <= t <= now + 600):
        return None
    out = {"e": ev["e"], "t": int(t), "i": ev["i"]}
    if "v" in ev:
        if not isinstance(ev["v"], str) or not _VER.match(ev["v"]):
            return None
        out["v"] = ev["v"]
    if "s" in ev:
        if ev["s"] not in (0, 1) or isinstance(ev["s"], bool):
            return None
        out["s"] = ev["s"]
    if "w" in ev:
        if ev["w"] not in ("s", "m", "l"):
            return None
        out["w"] = ev["w"]
    if "x" in ev:
        if not isinstance(ev["x"], str) or not _TAG.match(ev["x"]):
            return None
        out["x"] = ev["x"]
    return out


def configured():
    return bool(os.environ.get("NEXXUS_RELAY_URL", "").strip() and os.environ.get("NEXXUS_RELAY_KEY", "").strip())


def _call(path, body=None):
    base = os.environ["NEXXUS_RELAY_URL"].strip().rstrip("/")
    if not base.startswith("https://"):
        raise RuntimeError("NEXXUS_RELAY_URL must be an https:// address")
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST",
                                 headers={"Authorization": "Bearer " + os.environ["NEXXUS_RELAY_KEY"].strip(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read(2_000_000) or b"{}")


def _append(events):
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(STORE_PATH, "a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, separators=(",", ":")) + "\n")
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_STORED:
            with open(STORE_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-MAX_STORED:])
    except OSError:
        pass


def pull_once():
    """Fetch, validate and store one batch from the relay, then acknowledge it. -> {"received", "stored", "dropped"}; raises on a transport problem (nothing is acked then)."""
    if not configured():
        raise RuntimeError("set NEXXUS_RELAY_URL and NEXXUS_RELAY_KEY first")
    with _LOCK:
        batch = _call("/pull")
        items = batch.get("events") if isinstance(batch, dict) else None
        items = items if isinstance(items, list) else []
        good, keys = [], []
        for it in items[:500]:
            if isinstance(it, dict) and isinstance(it.get("k"), str):
                keys.append(it["k"][:80])
                clean = validate(it.get("ev"))
                if clean:
                    good.append(clean)
        if good:
            _append(good)
        if keys:
            _call("/ack", {"keys": keys})
        if items:
            try:
                with open(os.path.join(STORE_DIR, "pull_stats.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": int(time.time()), "received": len(items), "dropped": len(items) - len(good)}) + "\n")
            except OSError:
                pass
        return {"received": len(items), "stored": len(good), "dropped": len(items) - len(good)}


def summary(days=7):
    """Aggregate numbers only: events per name and per day, distinct installs, versions, standalone share."""
    cutoff = time.time() - days * 86400
    by_event, by_day, versions = collections.Counter(), collections.Counter(), collections.Counter()
    installs, standalone, total = set(), set(), 0
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("t", 0) < cutoff:
                    continue
                total += 1
                by_event[e["e"]] += 1
                by_day[time.strftime("%Y-%m-%d", time.gmtime(e["t"]))] += 1
                installs.add(e["i"])
                if e.get("v"):
                    versions[e["v"]] += 1
                if e.get("s") == 1:
                    standalone.add(e["i"])
    except OSError:
        pass
    return {"days": days, "events": total, "distinct_installs": len(installs), "installed_as_app": len(standalone), "by_event": dict(by_event),
            "by_day": dict(sorted(by_day.items())), "versions": dict(versions), "relay_configured": configured()}


_poller = {"thread": None, "stop": threading.Event()}


def start_poller(every=300):
    """Background pull every `every` seconds when a relay is configured. Safe to call more than once."""
    if not configured() or (_poller["thread"] and _poller["thread"].is_alive()):
        return False

    def loop():
        while not _poller["stop"].wait(every):
            try:
                pull_once()
            except Exception:
                pass          # relay down or offline: try again next round
    _poller["stop"].clear()
    _poller["thread"] = threading.Thread(target=loop, name="telemetry-poller", daemon=True)
    _poller["thread"].start()
    return True


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "pull":
        print(json.dumps(pull_once()))
    else:
        print(json.dumps(summary(), indent=2))
