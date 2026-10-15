"""feed_client.py - runs in EVERY copy of NEXXUS. Pulls the signed source feed published by the original NEXXUS and checks it. One-way: the copy asks for a file; nothing about the user is sent,
and nothing connects into the original.

    python feed_client.py fetch      download latest.json from NEXXUS_FEED_URL, verify it, keep it in feed_cache/
    python feed_client.py status     show the last verified feed (re-verified from disk every time, so an edited cache is caught)

Settings (environment): NEXXUS_FEED_URL  the address of latest.json (set once the feed is published; empty means "not configured")
                        NEXXUS_FEED_PUBKEY / NEXXUS_FEED_CACHE  override the public key file and the cache folder (tests use temp ones)
Only http(s) addresses are used, with a 10 s timeout and a size cap. A refused feed never replaces the one you already have. Standard library plus `cryptography`."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

import feed_core

ROOT = os.path.dirname(os.path.abspath(__file__))
PUB_PATH = os.environ.get("NEXXUS_FEED_PUBKEY") or os.path.join(ROOT, "feed_public_key.pem")
CACHE_DIR = os.environ.get("NEXXUS_FEED_CACHE") or os.path.join(ROOT, "feed_cache")


def feed_url():
    return os.environ.get("NEXXUS_FEED_URL", "").strip()


def _pub():
    try:
        with open(PUB_PATH, "rb") as f:
            return f.read()
    except OSError:
        raise feed_core.FeedError("the original's public key (feed_public_key.pem) is missing, so no feed can be verified")


def _state():
    try:
        with open(os.path.join(CACHE_DIR, "state.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"last_sequence": 0}


def _write_atomic(name, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = os.path.join(CACHE_DIR, name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, os.path.join(CACHE_DIR, name))


def status(now=None):
    """The last verified feed, re-checked from disk. -> {"ok", "message", "bundle"?, "stale"?, "age_s"?}"""
    p = os.path.join(CACHE_DIR, "latest.json")
    if not os.path.exists(p):
        return {"ok": False, "configured": bool(feed_url()), "message": "No feed has been downloaded yet." + ("" if feed_url() else " The feed address is not set up on this copy yet.")}
    try:
        with open(p, "rb") as f:
            r = feed_core.verify_bundle(f.read(), _pub(), last_sequence=0, now=now)
    except feed_core.FeedError as e:
        return {"ok": False, "configured": bool(feed_url()), "message": "The saved feed no longer verifies (%s). It will not be shown." % e}
    return {"ok": True, "configured": bool(feed_url()), "bundle": r["bundle"], "stale": r["stale"], "age_s": r["age_s"],
            "message": "Showing the last verified feed, %s." % ("older than its validity window" if r["stale"] else "within its validity window")}


def fetch(now=None):
    url = feed_url()
    if not url:
        return {"ok": False, "message": "The feed address is not set (NEXXUS_FEED_URL). Nothing was downloaded."}
    if not url.lower().startswith(("http://", "https://")):
        return {"ok": False, "message": "The feed address must start with http:// or https://. Nothing was downloaded."}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nexxus-feed-client/1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read(feed_core.MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError):
        s = status(now)
        return {"ok": False, "message": "Could not reach the feed (you may be offline, or the address is wrong). " + (s["message"] if s.get("ok") else "There is no saved copy yet.")}
    try:
        r = feed_core.verify_bundle(raw, _pub(), last_sequence=_state().get("last_sequence", 0), now=now)
    except feed_core.FeedError as e:
        return {"ok": False, "message": "Feed refused: %s. Your saved copy was not changed." % e}
    _write_atomic("latest.json", raw)
    _write_atomic("state.json", json.dumps({"last_sequence": r["bundle"]["sequence"], "fetched_at": int(now if now is not None else time.time())}).encode("utf-8"))
    return {"ok": True, "message": "Feed %d downloaded and verified." % r["bundle"]["sequence"], "bundle": r["bundle"], "stale": r["stale"], "age_s": r["age_s"]}


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "fetch":
        print(json.dumps({k: v for k, v in fetch().items() if k != "bundle"}, indent=1))
    elif cmd == "status":
        s = status()
        print(s["message"])
        if s.get("ok"):
            print(json.dumps(s["bundle"]["sections"], indent=1)[:4000])
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
