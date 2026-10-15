"""platform_mode.py - Platform mode: the two-sided spatial social space, locked behind the license gate in entitlements.py.

What this module does:
  * register_mode(): adds "platform" to the mode table and refuses to enter it unless a valid license is present (and drops back to Conversation if the license lapses while in it).
  * A LOCAL store in nexxus_data/platform/: your profile (left wall), and the floor: posts with optional photos, comments and 1-5 star ratings.
  * Live sync: every change is pushed instantly to every open viewport (a tab, a window, a phone on the dashboard's own network) over a Server-Sent Events stream, no refresh needed.
  * Routes: /api/platform/entitlement, /license, /state, /profile, /post, /post/<id>/comment, /post/<id>/rating, /media/<id>, /stream.

Photos: JPEG, PNG, GIF or WebP up to 6 MB. Each is opened with Pillow, rotated by its EXIF orientation, shrunk to 1600 px, and RE-ENCODED, so location and camera metadata (EXIF) are dropped and a file that merely
claims to be an image cannot be served as anything else. SVG is refused. Images are served with nosniff and a sandboxing CSP.

Honest about what is not here: there is no network of other people yet, so the right wall shows only what other people have really shared with you, which today is nothing. "Viewports" are the places
that open this same NEXXUS (your own devices); comments and ratings are yours. Connecting people is a server-side feature that does not exist in this build.
"""
import io
import json
import os
import queue
import re
import threading
import time
import uuid

import entitlements

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "nexxus_data", "platform")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.json")
POSTS_PATH = os.path.join(DATA_DIR, "posts.jsonl")
MEDIA_DIR = os.path.join(DATA_DIR, "media")
MODE = "platform"
MAX_POSTS = 500
MAX_TEXT = 500
MAX_COMMENT = 300
MAX_COMMENTS = 100
MAX_UPLOAD = 6 * 1024 * 1024
MAX_SIDE = 1600
MAX_PIXELS = 40_000_000
MAX_STREAMS = 20
POSTS_PER_MINUTE = 30
_LOCK = threading.RLock()
_URL = re.compile(r"https?://[^\s<>\"']{1,300}", re.I)
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MEDIA_ID = re.compile(r"^[0-9a-f]{16}$")
_recent_posts = []

MODE_DEF = {
    "label": "Platform", "can_build": False, "vault_lane": None, "commit_blocks_on": [],
    "summary": "Platform: your profile on the left wall, your network on the right, the live floor in the middle with the command bar at its base. Exit returns to the desktop dashboard.",
}


class ModeLocked(ValueError):
    """Raised when Platform mode is requested without a valid license (a ValueError so /api/mode answers 400 with the message)."""


class MediaError(ValueError):
    """A photo that was refused; the message says why."""


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


# ---------------------------------------------------------------- live sync (viewports)
_subs = []
_subs_lock = threading.Lock()


def subscribe():
    """-> a queue that receives every change as a dict, or None if too many viewports are open."""
    with _subs_lock:
        if len(_subs) >= MAX_STREAMS:
            return None
        q = queue.Queue(maxsize=200)
        _subs.append(q)
        return q


def unsubscribe(q):
    with _subs_lock:
        if q in _subs:
            _subs.remove(q)


def publish(event):
    with _subs_lock:
        targets = list(_subs)
    for q in targets:
        try:
            q.put_nowait(event)
        except queue.Full:                     # a stuck viewport must never slow the others; it will reload its state when it reconnects
            try:
                q.get_nowait()
                q.put_nowait(event)
            except (queue.Empty, queue.Full):
                pass


def viewers():
    with _subs_lock:
        return len(_subs)


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
    publish({"type": "profile", "profile": p})
    return p


def _norm(p):
    p.setdefault("media", "")
    p.setdefault("rating", 0)
    p.setdefault("comments", [])
    return p


def _read_posts():
    out = []
    try:
        with open(POSTS_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(_norm(json.loads(line)))
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


def _rate_ok():
    now = time.time()
    _recent_posts[:] = [t for t in _recent_posts if now - t < 60]
    if len(_recent_posts) >= POSTS_PER_MINUTE:
        return False
    _recent_posts.append(now)
    return True


def save_media(data):
    """Validate a photo and store a clean re-encoded copy. -> media id. Raises MediaError."""
    if not data or len(data) > MAX_UPLOAD:
        raise MediaError("The photo is empty or larger than 6 MB.")
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise MediaError("Photos need Pillow (pip install Pillow).")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
        img = Image.open(io.BytesIO(data))
        if img.format not in ("JPEG", "PNG", "GIF", "WEBP"):
            raise MediaError("Only JPEG, PNG, GIF and WebP photos are accepted.")
        img.seek(0)
        img = ImageOps.exif_transpose(img)
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        buf = io.BytesIO()
        if has_alpha:
            img.convert("RGBA").save(buf, "PNG", optimize=True)
            ext = "png"
        else:
            img.convert("RGB").save(buf, "JPEG", quality=85, optimize=True)
            ext = "jpg"
    except MediaError:
        raise
    except Exception:
        raise MediaError("That file is not a photo NEXXUS can read.")
    mid = uuid.uuid4().hex[:16]
    os.makedirs(MEDIA_DIR, exist_ok=True)
    with open(os.path.join(MEDIA_DIR, "%s.%s" % (mid, ext)), "wb") as f:
        f.write(buf.getvalue())
    return mid


def media_path(mid):
    """-> (path, content_type) for a stored photo, or None."""
    if not _MEDIA_ID.match(str(mid or "")):
        return None
    for ext, ctype in (("jpg", "image/jpeg"), ("png", "image/png")):
        p = os.path.join(MEDIA_DIR, "%s.%s" % (mid, ext))
        if os.path.isfile(p):
            return p, ctype
    return None


def _drop_media(mid):
    found = media_path(mid)
    if found:
        try:
            os.remove(found[0])
        except OSError:
            pass


def sweep_media(min_age=0):
    """Delete stored photos that no post uses (left behind when a file was in use during a delete, or a post was refused). Safe to call any time."""
    try:
        names = os.listdir(MEDIA_DIR)
    except OSError:
        return 0
    with _LOCK:
        used = {p.get("media") for p in _read_posts()}
        n = 0
        for name in names:
            mid, _, ext = name.partition(".")
            path = os.path.join(MEDIA_DIR, name)
            try:
                if mid not in used and ext in ("jpg", "png") and time.time() - os.path.getmtime(path) >= min_age:
                    os.remove(path)
                    n += 1
            except OSError:
                pass            # still in use: the next sweep gets it
    return n


def add_post(text, media_id=""):
    """The command bar: one message (and optionally one photo) to the floor. A web link in the text becomes a shared link. -> the saved post, or None if there is nothing to post."""
    text = _clean(text, MAX_TEXT)
    media_id = media_id if media_path(media_id) else ""
    if not text and not media_id:
        return None
    m = _URL.search(text)
    post = {"id": uuid.uuid4().hex[:12], "t": int(time.time()), "text": text, "kind": "link" if m else ("photo" if media_id else "post"),
            "url": _safe_url(m.group(0)) if m else "", "media": media_id, "rating": 0, "comments": []}
    with _LOCK:
        posts = _read_posts()
        posts.append(post)
        dropped = posts[:-MAX_POSTS] if len(posts) > MAX_POSTS else []
        _write_posts(posts)
    for old in dropped:
        _drop_media(old.get("media"))
    publish({"type": "post", "post": post})
    return post


def delete_post(pid):
    with _LOCK:
        posts = _read_posts()
        gone = [p for p in posts if p.get("id") == str(pid)]
        if not gone:
            return False
        _write_posts([p for p in posts if p.get("id") != str(pid)])
    _drop_media(gone[0].get("media"))
    sweep_media(min_age=60)                    # also clears anything an in-flight download kept open earlier
    publish({"type": "post_deleted", "id": str(pid)})
    return True


def _update(pid, fn):
    with _LOCK:
        posts = _read_posts()
        for p in posts:
            if p.get("id") == str(pid):
                result = fn(p)
                _write_posts(posts)
                return result, p
    return None, None


def set_rating(pid, n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if not 0 <= n <= 5:
        return None
    res, p = _update(pid, lambda post: post.__setitem__("rating", n) or n)
    if p is not None:
        publish({"type": "rating", "post_id": p["id"], "rating": n})
        return n
    return None


def add_comment(pid, text):
    text = _clean(text, MAX_COMMENT)
    if not text:
        return None
    c = {"id": uuid.uuid4().hex[:10], "t": int(time.time()), "text": text}

    def go(post):
        if len(post["comments"]) >= MAX_COMMENTS:
            return None
        post["comments"].append(c)
        return c
    res, p = _update(pid, go)
    if res:
        publish({"type": "comment", "post_id": p["id"], "comment": c})
    return res


def delete_comment(pid, cid):
    def go(post):
        before = len(post["comments"])
        post["comments"] = [c for c in post["comments"] if c.get("id") != str(cid)]
        return len(post["comments"]) < before
    res, p = _update(pid, go)
    if res:
        publish({"type": "comment_deleted", "post_id": p["id"], "id": str(cid)})
    return bool(res)


def state():
    posts = _read_posts()[-200:]
    return {"profile": get_profile(), "floor": posts, "shared_links": [p for p in posts if p.get("kind") == "link"][-20:],
            "viewers": viewers(),
            "network": {"connections": 0, "feed": [], "note": "No network yet: connections and posts from other people will appear here once networking exists. Nothing is invented."}}


# ---------------------------------------------------------------- routes
def register_routes(app, is_viewer, respond):
    """is_viewer() -> True when this request may use Platform (the dashboard's own page, or a device the dashboard's network rules already admit; writes from other devices need the admin token,
    which the server's peer guard enforces). respond(payload, status=200) -> a Flask response with the server's usual CORS headers."""
    from flask import Response, request, send_file

    def guard(need_license=True):
        if not is_viewer():
            return respond({"status": "error", "message": "Platform is only available from this NEXXUS's own dashboard."}, 403)
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
        if not _rate_ok():
            return respond({"status": "error", "message": "Slow down: too many posts in a minute."}, 429)
        mid = ""
        if (request.content_type or "").startswith("multipart/"):
            if (request.content_length or 0) > MAX_UPLOAD + 100_000:
                return respond({"status": "error", "message": "The photo is larger than 6 MB."}, 413)
            text = request.form.get("text", "")
            f = request.files.get("image")
            if f:
                try:
                    mid = save_media(f.read(MAX_UPLOAD + 1))
                except MediaError as e:
                    return respond({"status": "error", "message": str(e)}, 400)
        else:
            text = (request.get_json(silent=True) or {}).get("text", "")
        post = add_post(text, mid)
        if not post and mid:
            _drop_media(mid)
        return respond({"status": "success", "post": post}) if post else respond({"status": "error", "message": "Nothing to post."}, 400)

    @app.route("/api/platform/post/<pid>", methods=["DELETE", "OPTIONS"], endpoint="platform_post_delete")
    def post_delete_route(pid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        return respond({"status": "success"}) if delete_post(pid) else respond({"status": "error", "message": "No such post."}, 404)

    @app.route("/api/platform/post/<pid>/rating", methods=["POST", "OPTIONS"], endpoint="platform_rating")
    def rating_route(pid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        n = set_rating(pid, (request.get_json(silent=True) or {}).get("rating"))
        return respond({"status": "success", "rating": n}) if n is not None else respond({"status": "error", "message": "A rating is 0 to 5 on an existing post."}, 400)

    @app.route("/api/platform/post/<pid>/comment", methods=["POST", "OPTIONS"], endpoint="platform_comment")
    def comment_route(pid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        c = add_comment(pid, (request.get_json(silent=True) or {}).get("text", ""))
        return respond({"status": "success", "comment": c}) if c else respond({"status": "error", "message": "Nothing to comment on, or the post is full."}, 400)

    @app.route("/api/platform/post/<pid>/comment/<cid>", methods=["DELETE", "OPTIONS"], endpoint="platform_comment_delete")
    def comment_delete_route(pid, cid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        return respond({"status": "success"}) if delete_comment(pid, cid) else respond({"status": "error", "message": "No such comment."}, 404)

    @app.route("/api/platform/media/<mid>", methods=["GET"], endpoint="platform_media")
    def media_route(mid):
        g = guard()
        if g:
            return g
        found = media_path(mid)
        if not found:
            return respond({"status": "error", "message": "No such photo."}, 404)
        r = send_file(found[0], mimetype=found[1], max_age=3600)
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        r.headers["Cache-Control"] = "private, max-age=3600"
        return r

    @app.route("/api/platform/stream", methods=["GET"], endpoint="platform_stream")
    def stream_route():
        g = guard()
        if g:
            return g
        q = subscribe()
        if q is None:
            return respond({"status": "error", "message": "Too many viewports are open."}, 503)

        def gen():
            try:
                yield "retry: 2000\nevent: hello\ndata: {\"viewers\": %d}\n\n" % viewers()
                publish({"type": "viewers", "viewers": viewers()})
                while True:
                    try:
                        ev = q.get(timeout=15)
                        yield "data: %s\n\n" % json.dumps(ev)
                    except queue.Empty:
                        yield ": keep-alive\n\n"
            finally:                       # the viewport closed
                unsubscribe(q)
                publish({"type": "viewers", "viewers": viewers()})
        r = Response(gen(), mimetype="text/event-stream")
        r.headers["Cache-Control"] = "no-store"
        r.headers["X-Accel-Buffering"] = "no"
        return r
