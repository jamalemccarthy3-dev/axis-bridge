"""platform_mode.py - Platform mode: the two-sided spatial social space, locked behind the license gate in entitlements.py.

What this module does:
  * register_mode(): adds "platform" to the mode table and refuses to enter it unless a valid license is present (and drops back to Conversation if the license lapses while in it).
  * A small LOCAL store: your own profile (left wall) and your own posts and links on the floor. Everything is saved on this computer in nexxus_data/platform/.
  * Routes: /api/platform/entitlement, /license, /state, /profile, /post. Local machine only; the data routes also need a valid license.

Honest about what is not here: there is no network yet, so no other people. The right wall (network and friends feed) shows only what other people have really shared with you, which today is
nothing; it never shows invented posts or friends. Connecting people is a server-side feature that does not exist in this build.
"""
import json
import os
import re
import threading
import time
import uuid

import entitlements

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "nexxus_data", "platform")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.json")
POSTS_PATH = os.path.join(DATA_DIR, "posts.jsonl")
MODE = "platform"
MAX_POSTS = 500
MAX_TEXT = 500
_LOCK = threading.RLock()
_URL = re.compile(r"https?://[^\s<>\"']{1,300}", re.I)
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MODE_DEF = {
    "label": "Platform", "can_build": False, "vault_lane": None, "commit_blocks_on": [],
    "summary": "Platform: your profile on the left wall, your network on the right, the live floor in the middle with the command bar at its base. Exit returns to the desktop dashboard.",
}


class ModeLocked(ValueError):
    """Raised when Platform mode is requested without a valid license (a ValueError so /api/mode answers 400 with the message)."""


def register_mode(mode_state, modes_module):
    """Add the mode and the license guard to a ModeState. Safe to call once at startup."""
    modes_module.MODES.setdefault(MODE, MODE_DEF)
    original_set, original_snapshot = mode_state.set, mode_state.snapshot

    def guarded_set(mode):
        if mode == MODE and not entitlements.is_unlocked():
            raise ModeLocked("Platform mode is locked. Unlock it with a monthly subscription ($9.99/month) or the Lifetime Access Pass ($199) and add your license key.")
        return original_set(mode)

    def guarded_snapshot():
        if mode_state.mode == MODE and not entitlements.is_unlocked():
            original_set(modes_module.DEFAULT_MODE)           # the license lapsed: back to the standard desktop view
        return original_snapshot()

    mode_state.set, mode_state.snapshot = guarded_set, guarded_snapshot


# ---------------------------------------------------------------- local store
def _clean(s, n):
    return _CTRL.sub("", str(s or "")).strip()[:n]


def _safe_url(u):
    u = str(u or "").strip()
    return u if re.match(r"^https?://[^\s<>\"']{1,300}$", u, re.I) else ""


def get_profile():
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            p = json.load(f)
    except (OSError, ValueError):
        p = {}
    return {"name": p.get("name", ""), "headline": p.get("headline", ""), "location": p.get("location", ""), "about": p.get("about", ""), "links": [u for u in p.get("links", []) if _safe_url(u)][:5]}


def save_profile(d):
    p = {"name": _clean(d.get("name"), 60), "headline": _clean(d.get("headline"), 120), "location": _clean(d.get("location"), 60), "about": _clean(d.get("about"), 600),
         "links": [u for u in (_safe_url(x) for x in (d.get("links") or [])[:5]) if u]}
    with _LOCK:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = PROFILE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(p, f)
        os.replace(tmp, PROFILE_PATH)
    return p


def _read_posts():
    out = []
    try:
        with open(POSTS_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _write_posts(posts):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = POSTS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for p in posts[-MAX_POSTS:]:
            f.write(json.dumps(p) + "\n")
    os.replace(tmp, POSTS_PATH)


def add_post(text):
    """The command bar: one message to the floor. A web link in it becomes a shared link. -> the saved post, or None if empty."""
    text = _clean(text, MAX_TEXT)
    if not text:
        return None
    m = _URL.search(text)
    post = {"id": uuid.uuid4().hex[:12], "t": int(time.time()), "text": text, "kind": "link" if m else "post", "url": _safe_url(m.group(0)) if m else ""}
    with _LOCK:
        posts = _read_posts()
        posts.append(post)
        _write_posts(posts)
    return post


def delete_post(pid):
    with _LOCK:
        posts = _read_posts()
        kept = [p for p in posts if p.get("id") != str(pid)]
        if len(kept) == len(posts):
            return False
        _write_posts(kept)
    return True


def state():
    posts = _read_posts()[-200:]
    return {"profile": get_profile(), "floor": posts, "shared_links": [p for p in posts if p.get("kind") == "link"][-20:],
            "network": {"connections": 0, "feed": [], "note": "No network yet: connections and posts from other people will appear here once networking exists. Nothing is invented."}}


# ---------------------------------------------------------------- routes
def register_routes(app, is_local, respond):
    """respond(payload, status=200) -> a Flask response with the server's usual CORS headers."""
    from flask import request

    def guard(need_license=True):
        if not is_local():
            return respond({"status": "error", "message": "Platform is only available on the computer NEXXUS runs on."}, 403)
        if need_license and not entitlements.is_unlocked():
            return respond({"status": "locked", "message": "Platform mode is locked.", **entitlements.offer()}, 402)
        return None

    @app.route("/api/platform/entitlement", methods=["GET", "OPTIONS"], endpoint="platform_entitlement")
    def entitlement():
        if request.method == "OPTIONS":
            return respond({})
        return guard(False) or respond({"status": "success", **entitlements.offer()})

    @app.route("/api/platform/license", methods=["POST", "DELETE", "OPTIONS"], endpoint="platform_license")
    def license_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard(False)
        if g:
            return g
        if request.method == "DELETE":
            return respond({"status": "success", "entitlement": entitlements.remove()})
        ok, st = entitlements.activate((request.get_json(silent=True) or {}).get("token", ""))
        return respond({"status": "success" if ok else "error", "entitlement": st, "message": "Platform unlocked." if ok else st["reason"]}, 200 if ok else 400)

    @app.route("/api/platform/state", methods=["GET", "OPTIONS"], endpoint="platform_state")
    def state_route():
        if request.method == "OPTIONS":
            return respond({})
        return guard() or respond({"status": "success", **state()})

    @app.route("/api/platform/profile", methods=["POST", "OPTIONS"], endpoint="platform_profile")
    def profile_route():
        if request.method == "OPTIONS":
            return respond({})
        return guard() or respond({"status": "success", "profile": save_profile(request.get_json(silent=True) or {})})

    @app.route("/api/platform/post", methods=["POST", "OPTIONS"], endpoint="platform_post")
    def post_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        post = add_post((request.get_json(silent=True) or {}).get("text", ""))
        return respond({"status": "success", "post": post}) if post else respond({"status": "error", "message": "Nothing to post."}, 400)

    @app.route("/api/platform/post/<pid>", methods=["DELETE", "OPTIONS"], endpoint="platform_post_delete")
    def post_delete_route(pid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        return respond({"status": "success"}) if delete_post(pid) else respond({"status": "error", "message": "No such post."}, 404)
