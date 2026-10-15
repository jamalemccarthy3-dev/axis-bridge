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
import hashlib
import io
import json
import os
import queue
import re
import threading
import time
import uuid

import academy
import entitlements
import github_sync
import market_social
import marketplace
import marketplace_export
import privacy
import ranks
import teams

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "nexxus_data", "platform")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.json")
POSTS_PATH = os.path.join(DATA_DIR, "posts.jsonl")
MEDIA_DIR = os.path.join(DATA_DIR, "media")
VAULT_PATH = os.path.join(DATA_DIR, "vault.json")
MODE = "platform"
MAX_POSTS = 500
MAX_TEXT = 500
MAX_COMMENT = 300
MAX_COMMENTS = 100
MAX_UPLOAD = 6 * 1024 * 1024
MAX_SIDE = 1600
MAX_PIXELS = 40_000_000
MAX_STREAMS = 20
MAX_VAULT = 300
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


SECTIONS = ("about", "experience", "projects", "skills", "featured", "location", "links")
DEFAULT_VISIBLE = {"about": True, "experience": True, "projects": True, "skills": True, "featured": True, "location": False, "links": False}     # privacy first: contact-like details start hidden
MAX_FEATURED = 3


def _list_of_dicts(items, fields, limit):
    out = []
    for it in (items or [])[:limit * 5]:                 # skip junk entries first, then cap the real ones
        if len(out) >= limit:
            break
        if not isinstance(it, dict):
            continue
        row = {k: _clean(it.get(k), n) for k, n in fields.items() if k != "url"}
        if "url" in fields:
            row["url"] = _safe_url(it.get("url"))
        if any(row.get(k) for k in fields):
            out.append(row)
    return out


EXP_FIELDS = {"title": 80, "org": 80, "period": 40, "desc": 300}
PROJ_FIELDS = {"name": 80, "url": 300, "desc": 300}


def _profile_from(p):
    p = p if isinstance(p, dict) else {}
    vis = p.get("visible") if isinstance(p.get("visible"), dict) else {}
    skills, seen = [], set()
    for x in (p.get("skills") or [])[:40]:
        x = _clean(x, 30)
        if x and x.lower() not in seen:
            seen.add(x.lower()); skills.append(x)
    return {"name": _clean(p.get("name"), 60), "headline": _clean(p.get("headline"), 120), "location": _clean(p.get("location"), 60), "about": _clean(p.get("about"), 600),
            "links": [u for u in (_safe_url(x) for x in (p.get("links") or [])[:5]) if u], "skills": skills[:20],
            "experience": _list_of_dicts(p.get("experience"), EXP_FIELDS, 10), "projects": _list_of_dicts(p.get("projects"), PROJ_FIELDS, 10),
            "featured": [str(x)[:12] for x in (p.get("featured") or [])[:MAX_FEATURED] if isinstance(x, str)],
            "avatar": p.get("avatar") if _MEDIA_ID.match(str(p.get("avatar") or "")) else "",
            "visible": {k: bool(vis.get(k, DEFAULT_VISIBLE[k])) for k in SECTIONS}}


def get_profile():
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        raw = {}
    p = _profile_from(raw)
    ids = {x.get("id") for x in _read_posts()}
    p["featured"] = [x for x in p["featured"] if x in ids]                  # a deleted post leaves the featured shelf
    if p["avatar"] and not media_path(p["avatar"]):
        p["avatar"] = ""
    return p


def save_profile(d):
    """Merge the given fields into the profile (fields that are not sent keep their value), then clean everything again."""
    d = d if isinstance(d, dict) else {}
    cur = get_profile()
    merged = dict(cur, **{k: v for k, v in d.items() if k in cur and k != "visible"})
    merged["visible"] = dict(cur["visible"], **(d.get("visible") if isinstance(d.get("visible"), dict) else {}))
    p = _profile_from(merged)
    ids = {x.get("id") for x in _read_posts()}
    p["featured"] = [x for x in p["featured"] if x in ids]
    if p["avatar"] and not media_path(p["avatar"]):
        p["avatar"] = ""
    with _LOCK:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = PROFILE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(p, f)
        os.replace(tmp, PROFILE_PATH)
    publish({"type": "profile", "profile": p})
    return p


def visitor_view():
    """What someone visiting this profile sees: name and headline always, then only the sections the owner marked visible. Featured posts show their text, link and photo only: never comments,
    ratings, other posts, or anything private. This is the one place that decides, so a future network serves exactly this."""
    p = get_profile()
    v = p["visible"]
    out = {"name": p["name"], "headline": p["headline"], "avatar": p["avatar"], "sections": []}
    if v["location"] and p["location"]:
        out["location"] = p["location"]
    if v["about"] and p["about"]:
        out["about"] = p["about"]
    if v["experience"] and p["experience"]:
        out["experience"] = p["experience"]
    if v["projects"] and p["projects"]:
        out["projects"] = p["projects"]
    if v["skills"] and p["skills"]:
        out["skills"] = p["skills"]
    if v["links"] and p["links"]:
        out["links"] = p["links"]
    if v["featured"] and p["featured"]:
        by_id = {x.get("id"): x for x in _read_posts()}
        out["featured"] = [{"id": x, "text": by_id[x].get("text", ""), "url": by_id[x].get("url", ""), "media": by_id[x].get("media", ""), "t": by_id[x].get("t", 0)} for x in p["featured"] if x in by_id]
    out["sections"] = [k for k in ("about", "experience", "projects", "skills", "featured", "links", "location") if k in out]
    return out


def _norm(p):
    p.setdefault("media", "")
    p.setdefault("rating", 0)
    p.setdefault("comments", [])
    p.setdefault("public", False)
    p.setdefault("gh", None)
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
        used = {p.get("media") for p in _read_posts()} | {v.get("id") for v in _read_vault()} | {get_profile().get("avatar")}
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


def _read_vault():
    try:
        with open(VAULT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return [v for v in data if isinstance(v, dict) and _MEDIA_ID.match(str(v.get("id", "")))] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write_vault(items):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = VAULT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items[-MAX_VAULT:], f)
    os.replace(tmp, VAULT_PATH)


def vault_add(mid, name="", source="upload"):
    """Record a stored photo in the image vault (once). -> the vault item, or None if the photo does not exist."""
    found = media_path(mid)
    if not found:
        return None
    with _LOCK:
        items = _read_vault()
        for v in items:
            if v["id"] == mid:
                return v
        item = {"id": mid, "t": int(time.time()), "name": _clean(os.path.basename(str(name)), 60), "source": source if source in ("upload", "post") else "upload", "bytes": os.path.getsize(found[0])}
        items.append(item)
        dropped = items[:-MAX_VAULT] if len(items) > MAX_VAULT else []
        _write_vault(items)
    for old in dropped:
        _drop_media_if_unused(old["id"])
    publish({"type": "vault_added", "item": item})
    return item


def vault_list():
    items = [v for v in _read_vault() if media_path(v["id"])]
    used = {}
    for p in _read_posts():
        if p.get("media"):
            used.setdefault(p["media"], []).append(p["id"])
    avatar = get_profile().get("avatar")
    return [dict(v, posts=used.get(v["id"], []), avatar=(v["id"] == avatar)) for v in items]


def vault_delete(mid):
    """Remove a photo from the vault. The file itself goes only if no post and no profile photo still use it."""
    with _LOCK:
        items = _read_vault()
        kept = [v for v in items if v["id"] != str(mid)]
        if len(kept) == len(items):
            return False
        _write_vault(kept)
    _drop_media_if_unused(str(mid))
    publish({"type": "vault_deleted", "id": str(mid)})
    return True


def _drop_media_if_unused(mid):
    with _LOCK:
        if any(p.get("media") == mid for p in _read_posts()) or mid == get_profile().get("avatar") or any(v["id"] == mid for v in _read_vault()):
            return
    _drop_media(mid)


def add_post(text, media_id="", public=False):
    """The command bar: one message (and optionally one photo) to the floor. A web link in the text becomes a shared link. -> the saved post, or None if there is nothing to post."""
    text = _clean(text, MAX_TEXT)
    media_id = media_id if media_path(media_id) else ""
    if not text and not media_id:
        return None
    m = _URL.search(text)
    post = {"id": uuid.uuid4().hex[:12], "t": int(time.time()), "text": text, "kind": "link" if m else ("photo" if media_id else "post"),
            "url": _safe_url(m.group(0)) if m else "", "media": media_id, "rating": 0, "comments": [], "public": False, "gh": None}
    with _LOCK:
        posts = _read_posts()
        posts.append(post)
        dropped = posts[:-MAX_POSTS] if len(posts) > MAX_POSTS else []
        _write_posts(posts)
    if media_id:
        vault_add(media_id, text[:60], "post")
    for old in dropped:
        _drop_media_if_unused(old.get("media"))
    publish({"type": "post", "post": post})
    if public:
        set_public(post["id"], True)                 # shared from the start: it joins the public wall and the rank ledger like any public post
        post["public"] = True
    return post


def delete_post(pid):
    with _LOCK:
        posts = _read_posts()
        gone = [p for p in posts if p.get("id") == str(pid)]
        if not gone:
            return False
        _write_posts([p for p in posts if p.get("id") != str(pid)])
    if gone[0].get("media"):
        _drop_media_if_unused(gone[0]["media"])        # a photo that is also in the vault stays there
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


# ---------------------------------------------------------------- public wall, ranks, GitHub sync
_gh_transport = None            # tests inject a fake GitHub here; None means the real API
_gh_last_pull = [0.0]


def set_public(pid, flag):
    """Mark a post public (it may then appear on the public wall, be offered to the GitHub sync and earn rank points) or private again.
    -> "ok", "mirrored" (already a GitHub Discussion: it cannot be taken back from here) or None (no such post)."""
    flag = bool(flag)

    def go(post):
        if post.get("gh") and not flag:
            return "mirrored"
        post["public"] = flag
        return "ok"
    res, p = _update(pid, go)
    if p is None:
        return None
    if res == "ok":
        if flag:
            ranks.award("public_post", p["id"], (p.get("text") or "photo")[:40])
        else:
            ranks.revoke("public_post", p["id"])
        publish({"type": "public", "post_id": p["id"], "public": flag})
    return res


def public_wall():
    """Everything shared publicly, built only through the privacy gate. Never includes ratings, the vault, hidden profile sections or any private conversation."""
    out = []
    for p in _read_posts():
        if not p.get("public"):
            continue
        pub = privacy.require_public(privacy.as_public_post(p), "the public wall")
        pub["comments"] = [privacy.require_public(privacy.as_public_comment(p["id"], c), "the public wall") for c in p["comments"]]
        out.append(pub)
    return {"posts": out[-100:], "statement": privacy.PRIVATE_STATEMENT}


def github_status():
    return {"configured": github_sync.configured(), "repo": github_sync.repo(), "category": github_sync.category()}


def github_plan():
    """Public posts not yet on GitHub, with exactly what each would post. Nothing is sent."""
    items = []
    for p in _read_posts():
        if p.get("public") and not p.get("gh"):
            items.append(dict(github_sync.preview(p), id=p["id"]))
    return dict(github_status(), items=items)


def github_publish(pid):
    """Create the Discussion for ONE public post (the caller has already shown the preview and got a confirmation). -> the gh link."""
    post = next((x for x in _read_posts() if x.get("id") == str(pid)), None)
    if not post:
        raise github_sync.GitHubError("No such post.")
    if post.get("gh"):
        raise github_sync.GitHubError("That post is already on GitHub.")
    gh = github_sync.publish_post(post, _gh_transport)                  # raises PrivacyViolation if the post is not public
    _update(pid, lambda x: x.__setitem__("gh", gh))
    publish({"type": "github", "post_id": str(pid), "gh": gh})
    return gh


def github_pull():
    """Bring other people's public comments from the mirrored Discussions onto the wall, and award the (visible) rank points for them. -> {"new": n}."""
    now = time.time()
    if now - _gh_last_pull[0] < 10:
        raise github_sync.GitHubError("Pulled a moment ago; wait a few seconds.")
    _gh_last_pull[0] = now
    me = github_sync.viewer_login(_gh_transport).lower()
    new = 0
    for post in _read_posts():
        if not post.get("gh") or not post.get("public"):
            continue
        for c in github_sync.pull_comments(post["gh"]["id"], _gh_transport):
            lid = "gh" + hashlib.sha1(c["id"].encode()).hexdigest()[:8]
            if any(x.get("id") == lid for x in post["comments"]):
                continue
            entry = {"id": lid, "t": int(time.time()), "text": _clean(c["text"], MAX_COMMENT), "author": _clean(c["author"], 40), "source": "github", "url": c["url"] if str(c["url"]).startswith("https://github.com/") else ""}
            if not entry["text"]:
                continue

            def add(pp, e=entry):
                if len(pp["comments"]) >= MAX_COMMENTS:
                    return None
                pp["comments"].append(e)
                return e
            res, pp = _update(post["id"], add)
            if res:
                new += 1
                publish({"type": "comment", "post_id": post["id"], "comment": res})
                if res["author"].lower() != me:                          # no points for talking to yourself
                    ranks.award("peer_comment_received", c["id"], res["author"])
    return {"new": new}


def github_push_comment(pid, cid):
    """Post one of YOUR comments on a mirrored public post to its Discussion. -> {"url"}."""
    post = next((x for x in _read_posts() if x.get("id") == str(pid)), None)
    if not post or not post.get("gh") or not post.get("public"):
        raise github_sync.GitHubError("That post is not a public post mirrored on GitHub.")
    c = next((x for x in post["comments"] if x.get("id") == str(cid)), None)
    if not c or c.get("source") == "github":
        raise github_sync.GitHubError("Only your own comments can be posted to GitHub.")
    if c.get("pushed"):
        raise github_sync.GitHubError("That comment is already on GitHub.")
    r = github_sync.push_comment(post["gh"]["id"], privacy.as_public_comment(post["id"], c), _gh_transport)
    _update(pid, lambda x: [cc.update(pushed=True, url=r["url"]) for cc in x["comments"] if cc.get("id") == str(cid)])
    return {"url": r["url"]}


def _academy_context():
    """What the learner has really done, for the academy's own checks."""
    return {"profile": get_profile(), "posts": _read_posts(), "vault": _read_vault()}


academy.set_context_provider(_academy_context)
teams.set_providers(tracks=lambda: academy.overview()["tracks"])


def set_system_provider(fn):
    """The server gives teams a read-only way to see this NEXXUS's engines and hub (real telemetry, never invented)."""
    teams.set_providers(system=fn)


def state():
    posts = _read_posts()[-200:]
    return {"profile": get_profile(), "floor": posts, "shared_links": [p for p in posts if p.get("kind") == "link"][-20:],
            "viewers": viewers(), "vault_count": len(vault_list()), "rank": {k: v for k, v in ranks.status().items() if k in ("points", "tier", "next_tier", "to_next")},
            "network": {"connections": 0, "feed": [], "note": "No network yet: connections and posts from other people will appear here once networking exists. Nothing is invented."}}


# ---------------------------------------------------------------- routes
def register_routes(app, is_viewer, respond, is_admin=None):
    """is_viewer() -> True when this request may use Platform (the dashboard's own page, or a device the dashboard's network rules already admit; writes from other devices need the admin token,
    which the server's peer guard enforces). respond(payload, status=200) -> a Flask response with the server's usual CORS headers."""
    from flask import Response, request, send_file
    is_admin = is_admin or (lambda: False)           # no administrator unless the server says so: marketplace approvals fail closed

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

    @app.route("/api/platform/vault", methods=["GET", "POST", "OPTIONS"], endpoint="platform_vault")
    def vault_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        if request.method == "GET":
            return respond({"status": "success", "items": vault_list()})
        if not _rate_ok():
            return respond({"status": "error", "message": "Slow down: too many uploads in a minute."}, 429)
        if (request.content_length or 0) > MAX_UPLOAD + 100_000:
            return respond({"status": "error", "message": "The photo is larger than 6 MB."}, 413)
        f = request.files.get("image")
        if not f:
            return respond({"status": "error", "message": "Choose a photo to add."}, 400)
        try:
            item = vault_add(save_media(f.read(MAX_UPLOAD + 1)), f.filename or "", "upload")
        except MediaError as e:
            return respond({"status": "error", "message": str(e)}, 400)
        return respond({"status": "success", "item": item})

    @app.route("/api/platform/vault/<mid>", methods=["DELETE", "OPTIONS"], endpoint="platform_vault_delete")
    def vault_delete_route(mid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        return respond({"status": "success"}) if vault_delete(mid) else respond({"status": "error", "message": "No such photo in the vault."}, 404)

    @app.route("/api/platform/vault/<mid>/post", methods=["POST", "OPTIONS"], endpoint="platform_vault_post")
    def vault_post_route(mid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        if not any(v["id"] == mid for v in _read_vault()):
            return respond({"status": "error", "message": "No such photo in the vault."}, 404)
        if not _rate_ok():
            return respond({"status": "error", "message": "Slow down: too many posts in a minute."}, 429)
        post = add_post((request.get_json(silent=True) or {}).get("text", ""), mid)
        return respond({"status": "success", "post": post}) if post else respond({"status": "error", "message": "Could not post that photo."}, 400)

    @app.route("/api/platform/post/<pid>/public", methods=["POST", "OPTIONS"], endpoint="platform_public_flag")
    def public_flag_route(pid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        flag = bool((request.get_json(silent=True) or {}).get("public"))
        res = set_public(pid, flag)
        if res == "ok":
            return respond({"status": "success", "public": flag, "ranks": {"points": ranks.status()["points"], "tier": ranks.status()["tier"]}})
        if res == "mirrored":
            return respond({"status": "error", "message": "This post is already a GitHub Discussion, so it cannot be made private from here. Delete the Discussion on GitHub first."}, 409)
        return respond({"status": "error", "message": "No such post."}, 404)

    @app.route("/api/platform/public", methods=["GET", "OPTIONS"], endpoint="platform_public_wall")
    def public_wall_route():
        if request.method == "OPTIONS":
            return respond({})
        return guard() or respond({"status": "success", **public_wall()})

    @app.route("/api/platform/ranks", methods=["GET", "OPTIONS"], endpoint="platform_ranks")
    def ranks_route():
        if request.method == "OPTIONS":
            return respond({})
        return guard() or respond({"status": "success", **ranks.status()})

    @app.route("/api/platform/github/plan", methods=["GET", "OPTIONS"], endpoint="platform_github_plan")
    def github_plan_route():
        if request.method == "OPTIONS":
            return respond({})
        return guard() or respond({"status": "success", **github_plan()})

    def _gh(fn, *args):
        try:
            return respond({"status": "success", **fn(*args)})
        except (github_sync.GitHubError, privacy.PrivacyViolation) as e:
            return respond({"status": "error", "message": str(e)}, 400)

    @app.route("/api/platform/github/publish", methods=["POST", "OPTIONS"], endpoint="platform_github_publish")
    def github_publish_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        if d.get("confirm") is not True:
            return respond({"status": "error", "message": "Publishing puts this post on GitHub for everyone to read. Send confirm: true after showing the preview."}, 400)
        return _gh(lambda pid: {"gh": github_publish(pid)}, str(d.get("id", "")))

    @app.route("/api/platform/github/pull", methods=["POST", "OPTIONS"], endpoint="platform_github_pull")
    def github_pull_route():
        if request.method == "OPTIONS":
            return respond({})
        return guard() or _gh(github_pull)

    @app.route("/api/platform/post/<pid>/comment/<cid>/github", methods=["POST", "OPTIONS"], endpoint="platform_github_comment")
    def github_comment_route(pid, cid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        if (request.get_json(silent=True) or {}).get("confirm") is not True:
            return respond({"status": "error", "message": "This comment becomes public on GitHub. Send confirm: true after showing it."}, 400)
        return _gh(github_push_comment, pid, cid)

    @app.route("/api/platform/academy", methods=["GET", "OPTIONS"], endpoint="platform_academy")
    def academy_route():
        if request.method == "OPTIONS":
            return respond({})
        return guard() or respond({"status": "success", **academy.overview()})

    @app.route("/api/platform/academy/track/<tid>", methods=["GET", "OPTIONS"], endpoint="platform_academy_track")
    def academy_track_route(tid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        tr = academy.track_detail(tid)
        return respond({"status": "success", "track": tr}) if tr else respond({"status": "error", "message": "No such track."}, 404)

    @app.route("/api/platform/academy/path", methods=["POST", "OPTIONS"], endpoint="platform_academy_path")
    def academy_path_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        try:
            st = academy.set_path(str(d.get("path", "")), d.get("track") or None)
        except academy.AcademyError as e:
            return respond({"status": "error", "message": str(e)}, 400)
        publish({"type": "academy"})
        return respond({"status": "success", "state": st})

    @app.route("/api/platform/academy/conduct", methods=["POST", "OPTIONS"], endpoint="platform_academy_conduct")
    def academy_conduct_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        publish({"type": "academy"})
        return respond({"status": "success", "conduct": academy.acknowledge_conduct()})

    @app.route("/api/platform/academy/step", methods=["POST", "OPTIONS"], endpoint="platform_academy_step")
    def academy_step_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        try:
            res = academy.complete_step(str(d.get("track", "")), str(d.get("step", "")), d.get("evidence", ""))
        except academy.AcademyError as e:
            return respond({"status": "error", "message": str(e)}, 400)
        publish({"type": "academy"})
        return respond({"status": "success", **res})

    def _team(fn, *args, **kw):
        try:
            res = fn(*args, **kw)
        except teams.TeamError as e:
            return respond({"status": "error", "message": str(e)}, 404 if "No such" in str(e) else 400)
        publish({"type": "team"})
        return res

    @app.route("/api/platform/teams", methods=["GET", "POST", "OPTIONS"], endpoint="platform_teams")
    def teams_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        if request.method == "GET":
            return respond({"status": "success", "teams": teams.list_teams(), "limits": {"teams": teams.MAX_TEAMS, "tasks": teams.MAX_TASKS}})
        d = request.get_json(silent=True) or {}
        res = _team(teams.create_team, d.get("name"), d.get("mission", ""), d.get("kind", "team"), get_profile().get("name") or "You")
        return res if not isinstance(res, dict) else respond({"status": "success", "team": res})

    @app.route("/api/platform/teams/<tid>", methods=["GET", "DELETE", "OPTIONS"], endpoint="platform_team")
    def team_route(tid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        try:
            if request.method == "GET":
                return respond({"status": "success", "team": teams.get_team(tid)})
            teams.delete_team(tid)
        except teams.TeamError as e:
            return respond({"status": "error", "message": str(e)}, 404)
        publish({"type": "team"})
        return respond({"status": "success"})

    @app.route("/api/platform/teams/<tid>/task", methods=["POST", "OPTIONS"], endpoint="platform_team_task")
    def team_task_route(tid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        res = _team(teams.add_task, tid, d.get("title"), d.get("detail", ""), d.get("due", ""))
        return res if not isinstance(res, dict) else respond({"status": "success", "task": res})

    @app.route("/api/platform/teams/<tid>/task/<xid>", methods=["POST", "DELETE", "OPTIONS"], endpoint="platform_team_task_item")
    def team_task_item_route(tid, xid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        if request.method == "DELETE":
            res = _team(teams.delete_task, tid, xid)
            return res if res is not None else respond({"status": "success"})
        res = _team(teams.move_task, tid, xid, (request.get_json(silent=True) or {}).get("status"))
        return res if not isinstance(res, dict) else respond({"status": "success", "task": res})

    @app.route("/api/platform/teams/<tid>/blueprint", methods=["POST", "OPTIONS"], endpoint="platform_team_blueprint")
    def team_blueprint_route(tid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        res = _team(teams.attach_track, tid, str(d.get("track", "")), bool(d.get("on", True)))
        return res if not isinstance(res, list) else respond({"status": "success", "tracks": res})

    @app.route("/api/platform/academy/welcome", methods=["POST", "OPTIONS"], endpoint="platform_academy_welcome")
    def academy_welcome_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        publish({"type": "academy"})
        return respond({"status": "success", "welcomed": academy.mark_welcomed()})

    # ---------------- Marketplace: the storefront (buyers) and the vetting pipeline (creators and the administrator)
    def _admin_only():
        if not is_admin():
            return respond({"status": "error", "message": "This needs the administrator: unlock the admin token with the lock button in the header."}, 403)
        return None

    def _mk(fn, *args, **kw):
        try:
            res = fn(*args, **kw)
        except marketplace.MarketError as e:
            return respond({"status": "error", "message": str(e)}, 404 if "No such" in str(e) else 400)
        publish({"type": "market"})
        return res

    def _own_company_ids():
        return {t["id"] for t in teams.list_teams() if t["kind"] == "company"} | {"free"}           # "free" holds the free submissions made from this NEXXUS

    @app.route("/api/platform/marketplace/me", methods=["GET", "OPTIONS"], endpoint="platform_market_me")
    def market_me_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        return respond({"status": "success", "admin": bool(is_admin()), "companies": [{"id": t["id"], "name": t["name"]} for t in teams.list_teams() if t["kind"] == "company"], "tiers": list(marketplace.TIERS), "foss_licenses": list(marketplace.FOSS_LICENSES),
                        "categories": list(marketplace.CATEGORIES), "kinds": list(marketplace.KINDS), "permissions": list(marketplace.PERMISSIONS), "licenses": list(marketplace.LICENSES),
                        "revenue_share_percent": marketplace.REVENUE_SHARE_PERCENT, "limits": {"zip_mb": marketplace.MAX_ZIP // 1048576, "files": marketplace.MAX_ENTRIES}})

    @app.route("/api/platform/marketplace/catalog", methods=["GET", "OPTIONS"], endpoint="platform_market_catalog")
    def market_catalog_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        return respond({"status": "success", **marketplace.public_catalog(request.args.get("q", ""), request.args.get("category", ""), request.args.get("sort", "new"), None, request.args.get("tier", "all"))})

    @app.route("/api/platform/marketplace/product/<sid>", methods=["GET", "OPTIONS"], endpoint="platform_market_product")
    def market_product_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        try:
            return respond({"status": "success", "product": marketplace.public_product(sid)})
        except marketplace.MarketError as e:
            return respond({"status": "error", "message": str(e)}, 404)

    @app.route("/api/platform/marketplace/report", methods=["POST", "OPTIONS"], endpoint="platform_market_report")
    def market_report_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        res = _mk(marketplace.report_listing, str(d.get("id", "")), d.get("reason", ""), get_profile().get("name") or "visitor")
        return res if res is not None else respond({"status": "success"})

    @app.route("/api/platform/marketplace/mine", methods=["GET", "OPTIONS"], endpoint="platform_market_mine")
    def market_mine_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        return respond({"status": "success", "submissions": marketplace.list_submissions(_own_company_ids())})

    @app.route("/api/platform/marketplace/submission", methods=["POST", "OPTIONS"], endpoint="platform_market_create")
    def market_create_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        res = _mk(marketplace.create_submission, str(d.get("team_id", "")), d.get("listing"), get_profile().get("name") or "you", str(d.get("tier", "commercial")))
        return res if not isinstance(res, dict) else respond({"status": "success", "submission": marketplace.creator_view(res)})

    @app.route("/api/platform/marketplace/submission/<sid>", methods=["GET", "OPTIONS"], endpoint="platform_market_get")
    def market_get_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        try:
            sub = marketplace.get_submission(sid)
        except marketplace.MarketError as e:
            return respond({"status": "error", "message": str(e)}, 404)
        if sub["team_id"] not in _own_company_ids() and not is_admin():
            return respond({"status": "error", "message": "No such submission."}, 404)
        return respond({"status": "success", "submission": sub})

    @app.route("/api/platform/marketplace/submission/<sid>/upload", methods=["POST", "OPTIONS"], endpoint="platform_market_upload")
    def market_upload_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        try:
            sub = next((s for s in marketplace.list_submissions() if s["id"] == sid), None)
            if not sub or (sub["team_id"] not in _own_company_ids() and not is_admin()):
                return respond({"status": "error", "message": "No such submission."}, 404)
            if (request.content_length or 0) > marketplace.MAX_ZIP + 200_000:
                return respond({"status": "error", "message": "The bundle is larger than %d MB." % (marketplace.MAX_ZIP // 1048576)}, 413)
            f = request.files.get("bundle")
            if not f:
                return respond({"status": "error", "message": "Choose a .zip bundle."}, 400)
            data = f.read(marketplace.MAX_ZIP + 1)
            marketplace.upload_version(sid, data, f.filename or "")
        except marketplace.MarketError as e:
            return respond({"status": "error", "message": str(e)}, 400)
        publish({"type": "market"})
        return respond({"status": "success", "submission": marketplace.get_submission(sid)})

    @app.route("/api/platform/marketplace/submission/<sid>/agreement", methods=["POST", "OPTIONS"], endpoint="platform_market_agreement")
    def market_agreement_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        res = _mk(marketplace.sign_agreement, sid, d.get("legal_name", ""), d.get("acks"))
        return res if not isinstance(res, dict) else respond({"status": "success", "submission": marketplace.creator_view(res)})

    @app.route("/api/platform/marketplace/submission/<sid>/declaration", methods=["POST", "OPTIONS"], endpoint="platform_market_declaration")
    def market_declaration_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        res = _mk(marketplace.sign_declaration, sid, d.get("legal_name", ""), d.get("acks"))
        return res if not isinstance(res, dict) else respond({"status": "success", "submission": marketplace.creator_view(res)})

    def _who():
        return get_profile().get("name") or "you"

    @app.route("/api/platform/marketplace/product/<sid>/page", methods=["GET", "OPTIONS"], endpoint="platform_market_page")
    def market_page_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        try:
            page = marketplace.product_page(sid)
            soc = {"rating": market_social.summary(sid), "reviews": market_social.reviews(sid), "comments": market_social.comment_tree(sid)}
            ok, why = market_social.can_review(sid, _who(), page["tier"], page["owner"])
            soc["can_review"] = {"ok": ok, "reason": why}
            return respond({"status": "success", **page, "social": soc, "me": _who()})
        except marketplace.MarketError as e:
            return respond({"status": "error", "message": str(e)}, 404)

    @app.route("/api/platform/marketplace/product/<sid>/review", methods=["POST", "OPTIONS"], endpoint="platform_market_review_post")
    def market_review_post_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        try:
            res = market_social.add_review(sid, _who(), d.get("stars"), d.get("text", ""), marketplace.tier_of(sid), marketplace.owner_of(sid))
        except (market_social.SocialError, marketplace.MarketError) as e:
            return respond({"status": "error", "message": str(e)}, 400)
        publish({"type": "market"})
        return respond({"status": "success", "rating": res})

    @app.route("/api/platform/marketplace/product/<sid>/comment", methods=["POST", "OPTIONS"], endpoint="platform_market_comment_post")
    def market_comment_post_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        d = request.get_json(silent=True) or {}
        try:
            marketplace.public_product(sid)
            c = market_social.add_comment(sid, _who(), d.get("text", ""), d.get("parent") or None)
        except (market_social.SocialError, marketplace.MarketError) as e:
            return respond({"status": "error", "message": str(e)}, 400)
        publish({"type": "market"})
        return respond({"status": "success", "comment": c})

    @app.route("/api/platform/marketplace/comment/<cid>", methods=["DELETE", "OPTIONS"], endpoint="platform_market_comment_delete")
    def market_comment_delete_route(cid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        try:
            owner_of_product = False
            for pid, rows in market_social._load(market_social.COMMENTS_PATH, {}).items():
                if any(r["id"] == cid for r in rows):
                    owner_of_product = marketplace.owner_of(pid) == _who()
            market_social.remove_comment(cid, _who(), bool(is_admin()), owner_of_product)
        except (market_social.SocialError, marketplace.MarketError) as e:
            return respond({"status": "error", "message": str(e)}, 403 if "Only" in str(e) else 404)
        publish({"type": "market"})
        return respond({"status": "success"})

    @app.route("/api/platform/marketplace/product/<sid>/verify-purchase", methods=["POST", "OPTIONS"], endpoint="platform_market_verify_purchase")
    def market_verify_purchase_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard() or _admin_only()
        if g:
            return g
        who = str((request.get_json(silent=True) or {}).get("reviewer", "")).strip()
        try:
            marketplace.public_product(sid)
            market_social.record_interaction(sid, who, "purchase")
        except (market_social.SocialError, marketplace.MarketError) as e:
            return respond({"status": "error", "message": str(e)}, 400)
        return respond({"status": "success"})

    @app.route("/api/platform/marketplace/export", methods=["POST", "OPTIONS"], endpoint="platform_market_export")
    def market_export_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard() or _admin_only()
        if g:
            return g
        base = str((request.get_json(silent=True) or {}).get("base_url", ""))
        try:
            files = marketplace_export.build_site(os.path.join(marketplace.DATA_DIR, "site"), base)
        except marketplace.MarketError as e:
            return respond({"status": "error", "message": str(e)}, 400)
        return respond({"status": "success", "folder": os.path.join("nexxus_data", "marketplace", "site"), "files": files, "note": "Publish this folder yourself (for example to GitHub Pages). Nothing was uploaded."})

    @app.route("/api/platform/marketplace/free/<sid>/files", methods=["GET", "OPTIONS"], endpoint="platform_market_free_files")
    def market_free_files_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        try:
            return respond({"status": "success", **marketplace.free_files(sid)})
        except marketplace.MarketError as e:
            return respond({"status": "error", "message": str(e)}, 404)

    @app.route("/api/platform/marketplace/free/<sid>/file", methods=["GET", "OPTIONS"], endpoint="platform_market_free_file")
    def market_free_file_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        try:
            return respond({"status": "success", **marketplace.free_read(sid, request.args.get("name", ""))})
        except marketplace.MarketError as e:
            return respond({"status": "error", "message": str(e)}, 404)

    @app.route("/api/platform/marketplace/free/<sid>/download", methods=["GET"], endpoint="platform_market_free_download")
    def market_free_download_route(sid):
        g = guard()
        if g:
            return g
        try:
            data, filename, sha = marketplace.free_download(sid)
        except marketplace.MarketError as e:
            return respond({"status": "error", "message": str(e)}, 404)
        try:
            market_social.record_interaction(sid, _who(), "download")
        except market_social.SocialError:
            pass
        r = Response(data, mimetype="application/zip")
        r.headers["Content-Disposition"] = 'attachment; filename="%s"' % filename
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["X-Bundle-SHA256"] = sha
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.route("/api/platform/marketplace/submission/<sid>/approve", methods=["POST", "OPTIONS"], endpoint="platform_market_approve")
    def market_approve_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        d = request.get_json(silent=True) or {}
        return _admin_action(marketplace.approve_free, sid, d.get("admin", "admin"), d.get("note", ""))

    @app.route("/api/platform/marketplace/submission/<sid>/withdraw", methods=["POST", "OPTIONS"], endpoint="platform_market_withdraw")
    def market_withdraw_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        g = guard()
        if g:
            return g
        res = _mk(marketplace.withdraw, sid, get_profile().get("name") or "you")
        return res if not isinstance(res, dict) else respond({"status": "success"})

    @app.route("/api/platform/marketplace/admin/queue", methods=["GET", "OPTIONS"], endpoint="platform_market_queue")
    def market_queue_route():
        if request.method == "OPTIONS":
            return respond({})
        g = guard() or _admin_only()
        if g:
            return g
        return respond({"status": "success", "submissions": marketplace.list_submissions(), "reports": marketplace.reports(), "audit": marketplace.audit(100)})

    def _admin_action(fn, *args):
        g = guard() or _admin_only()
        if g:
            return g
        res = _mk(fn, *args)
        return res if not isinstance(res, dict) else respond({"status": "success", "submission": marketplace.creator_view(res)})

    @app.route("/api/platform/marketplace/submission/<sid>/attest", methods=["POST", "OPTIONS"], endpoint="platform_market_attest")
    def market_attest_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        d = request.get_json(silent=True) or {}
        return _admin_action(marketplace.attest_tests, sid, d.get("reviewer", ""), d.get("report", ""), d.get("environment", ""), d.get("passed", 0), d.get("failed", 0))

    @app.route("/api/platform/marketplace/submission/<sid>/review", methods=["POST", "OPTIONS"], endpoint="platform_market_review")
    def market_review_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        d = request.get_json(silent=True) or {}
        return _admin_action(marketplace.review_signoff, sid, d.get("reviewer", ""), d.get("checklist"), d.get("notes", ""), d.get("approve") is True)

    @app.route("/api/platform/marketplace/submission/<sid>/greenlight", methods=["POST", "OPTIONS"], endpoint="platform_market_greenlight")
    def market_greenlight_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        d = request.get_json(silent=True) or {}
        return _admin_action(marketplace.greenlight, sid, d.get("admin", "admin"), d.get("checkout_url", ""), d.get("discount"))

    @app.route("/api/platform/marketplace/submission/<sid>/checkout", methods=["POST", "OPTIONS"], endpoint="platform_market_checkout")
    def market_checkout_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        d = request.get_json(silent=True) or {}
        return _admin_action(marketplace.set_checkout, sid, d.get("admin", "admin"), d.get("checkout_url", ""), d.get("discount"))

    @app.route("/api/platform/marketplace/submission/<sid>/reject", methods=["POST", "OPTIONS"], endpoint="platform_market_reject")
    def market_reject_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        d = request.get_json(silent=True) or {}
        return _admin_action(marketplace.reject, sid, d.get("admin", "admin"), d.get("reason", ""))

    @app.route("/api/platform/marketplace/submission/<sid>/unpublish", methods=["POST", "OPTIONS"], endpoint="platform_market_unpublish")
    def market_unpublish_route(sid):
        if request.method == "OPTIONS":
            return respond({})
        d = request.get_json(silent=True) or {}
        return _admin_action(marketplace.unpublish, sid, d.get("admin", "admin"), d.get("reason", ""))

    @app.route("/api/platform/profile/public", methods=["GET", "OPTIONS"], endpoint="platform_profile_public")
    def profile_public_route():
        if request.method == "OPTIONS":
            return respond({})
        return guard() or respond({"status": "success", "profile": visitor_view()})

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
        wants_public = False
        if (request.content_type or "").startswith("multipart/"):
            if (request.content_length or 0) > MAX_UPLOAD + 100_000:
                return respond({"status": "error", "message": "The photo is larger than 6 MB."}, 413)
            text = request.form.get("text", "")
            wants_public = request.form.get("public") in ("1", "true", "yes")
            f = request.files.get("image")
            if f:
                try:
                    mid = save_media(f.read(MAX_UPLOAD + 1))
                except MediaError as e:
                    return respond({"status": "error", "message": str(e)}, 400)
        else:
            body = request.get_json(silent=True) or {}
            text = body.get("text", "")
            wants_public = body.get("public") is True
        post = add_post(text, mid, public=wants_public)
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
