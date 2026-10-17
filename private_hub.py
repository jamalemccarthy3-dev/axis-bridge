"""private_hub.py - the PRIVATE side of Platform: your conversations with the local NEXXUS, with auto-save and an archive grouped by day.

Everything here lives in the private folder (privacy.PRIVATE_DIR), which no public module may read. Nothing in this store is ever posted, shown on the public wall, sent to GitHub, counted for ranks, or served
to anyone but this computer's own dashboard. The public side is only what you choose to send through Post & Publish (Shared post).

What is NOT here: direct messages, friends, group chats and calls between people. Those need a shared network (accounts, delivery, moderation) and do not exist yet; the messaging hub says so plainly.

Sessions: a session is one conversation. Every message is saved the moment it is sent (auto-save), so nothing is lost if the window closes. The archive groups sessions as Today, Yesterday, Earlier this week
and Older, and any session can be opened, continued or deleted for good.
"""
import json
import os
import re
import tempfile
import threading
import time
import uuid

import privacy

STORE_PATH = os.path.join(privacy.PRIVATE_DIR, "talk_sessions.json")
MAX_SESSIONS = 200
MAX_MESSAGES = 500
MAX_TEXT = 6000
_LOCK = threading.RLock()
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TalkError(ValueError):
    pass


def _clean(s, n):
    return _CTRL.sub("", str(s or "")).strip()[:n]


def _read():
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _write(sessions):
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STORE_PATH), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(sessions, f)
    os.replace(tmp, STORE_PATH)


def _find(sessions, sid):
    for s in sessions:
        if s["id"] == str(sid):
            return s
    raise TalkError("No such conversation.")


def new_session(title=""):
    now = int(time.time())
    with _LOCK:
        sessions = _read()
        s = {"id": uuid.uuid4().hex[:12], "title": _clean(title, 80), "started": now, "updated": now, "messages": []}
        sessions.append(s)
        sessions.sort(key=lambda x: x["updated"])
        _write(sessions[-MAX_SESSIONS:])
    return s


def add_message(sid, who, text, cls=""):
    """Auto-save one message. who is 'me' or 'ai'."""
    if who not in ("me", "ai"):
        raise TalkError("A message is from you or from NEXXUS.")
    text = _clean(text, MAX_TEXT)
    if not text:
        raise TalkError("Nothing to save.")
    with _LOCK:
        sessions = _read()
        s = _find(sessions, sid)
        if len(s["messages"]) >= MAX_MESSAGES:
            raise TalkError("This conversation is full. Start a new one; this one stays in the archive.")
        now = int(time.time())
        s["messages"].append({"who": who, "text": text, "t": now, "cls": "err" if cls == "err" else ""})
        if not s["title"] and who == "me":
            s["title"] = _clean(text, 60)               # the first thing you said names the conversation
        s["updated"] = now
        _write(sessions)
    return s


def get(sid):
    return _find(_read(), sid)


def delete(sid):
    """Permanent. The conversation is removed from this computer."""
    with _LOCK:
        sessions = _read()
        s = _find(sessions, sid)
        _write([x for x in sessions if x["id"] != s["id"]])
    return {"deleted": s["id"]}


def _bucket(t, now):
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    day = time.strftime("%Y-%m-%d", time.localtime(t))
    if day == today:
        return "Today"
    if day == time.strftime("%Y-%m-%d", time.localtime(now - 86400)):
        return "Yesterday"
    if now - t < 7 * 86400:
        return "Earlier this week"
    return "Older"


ORDER = ("Today", "Yesterday", "Earlier this week", "Older")


def archive(now=None):
    """-> {"groups": [{"label", "items": [{id, title, updated, count}]}], "current": the most recent session or None}. Empty groups are left out."""
    now = now or time.time()
    sessions = sorted(_read(), key=lambda x: x["updated"], reverse=True)
    groups = {k: [] for k in ORDER}
    for s in sessions:
        if s["messages"]:
            groups[_bucket(s["updated"], now)].append({"id": s["id"], "title": s["title"] or "Untitled conversation", "updated": s["updated"], "count": len(s["messages"])})
    return {"groups": [{"label": k, "items": groups[k]} for k in ORDER if groups[k]], "current": sessions[0] if sessions else None}


STATEMENT = ("Everything in here is private: it stays on this computer, is saved automatically, and is never posted, never on the public wall, never sent to GitHub and never counted for ranks. "
             "Only what you send with Post & Publish (Shared post) is public.")

HUB = {
    "title": "Private messages and friends",
    "statement": ("Everything in this space is 100% private. It is never posted, never on the public wall, never sent to GitHub and never counted for ranks. "
                  "Only what you send with Post & Publish (Shared post) is public."),
    "sections": [
        {"id": "friends", "title": "Friends", "available": False, "text": "Your friends list is empty. Adding friends needs the shared network (accounts, requests and moderation), which is not built yet."},
        {"id": "messages", "title": "Direct messages", "available": False, "text": "Texting a friend needs the shared network. Nothing here is faked: when it exists, messages stay in this private space."},
        {"id": "groups", "title": "Group chats", "available": False, "text": "Group chats need the shared network and a server that can deliver to several people."},
        {"id": "calls", "title": "Phone and video calls", "available": False, "text": "Calls need live-room signalling on a shared server; business phone lines also need a telephony provider account. Not available yet."},
    ],
    "now": "What works today: Talk to NEXXUS is a private line to the NEXXUS on this computer, with auto-save and an archive.",
}


def register_routes(app, guard, respond):
    """guard() -> a response to return (refused) or None; respond(payload, status) builds a response. Called by platform_mode.register_routes."""
    from flask import request

    @app.route("/api/platform/private/hub", methods=["GET", "OPTIONS"], endpoint="private_hub")
    def hub_route():
        if request.method == "OPTIONS":
            return respond({})
        return guard() or respond({"status": "success", **HUB})

    @app.route("/api/platform/private/talk", methods=["GET", "POST", "OPTIONS"], endpoint="private_talk")
    def talk_route():
        """GET the archive and the latest conversation; POST starts a new conversation."""
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        if request.method == "POST":
            return respond({"status": "success", "session": new_session(), "statement": STATEMENT})
        return respond({"status": "success", **archive(), "statement": STATEMENT})

    @app.route("/api/platform/private/talk/<sid>", methods=["GET", "DELETE", "OPTIONS"], endpoint="private_talk_item")
    def talk_item_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        try:
            if request.method == "DELETE":
                return respond({"status": "success", **delete(sid)})
            return respond({"status": "success", "session": get(sid)})
        except TalkError as e:
            return respond({"status": "error", "message": str(e)}, 404)

    @app.route("/api/platform/private/talk/<sid>/message", methods=["POST", "OPTIONS"], endpoint="private_talk_message")
    def talk_message_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        try:
            s = add_message(sid, str(d.get("who", "")), d.get("text", ""), str(d.get("cls", "")))
        except TalkError as e:
            return respond({"status": "error", "message": str(e)}, 400)
        return respond({"status": "success", "saved": len(s["messages"])})
