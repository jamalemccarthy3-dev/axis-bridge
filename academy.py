"""academy.py - the NEXXUS Academy: the curriculum, your progress and the badges that prove it.

Platform mode is a digital academy. People work through tracks (a track has modules, a module has steps). Each step teaches one thing with the exact prompts, commands and tips to do it, and says how
you know you are done. Badges are the proof: they are earned by finishing modules and tracks, and each badge says HOW it was proved:

  verified       every step behind it was checked by NEXXUS itself against what you really did (for example "you wrote a public post of at least 40 characters")
  self-reported  the steps ask you to write what you did; NEXXUS cannot check it and says so on the badge
  mixed          some of each

Nothing is faked and nothing is hidden: the criteria for every badge are listed, and your badge ledger is append-only. In the open Beta every track is open from day one (no prerequisites, no payment).

The leadership loop: finishing a whole track earns "Mentor-ready". Mentoring itself (being matched with a learner and reviewing their work) needs other people on the platform and is not built yet; the badge
says exactly that.

Content lives in academy/curriculum/*.json and is validated on load; a video can be attached to a step only from an allow-listed host and is click-to-load (see academy/README.md).
"""
import glob
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CURRICULUM_DIR = os.path.join(HERE, "academy", "curriculum")
PROGRESS_PATH = os.path.join(HERE, "nexxus_data", "platform", "academy.json")
BADGES_PATH = os.path.join(HERE, "nexxus_data", "platform", "badges.jsonl")
CONDUCT_VERSION = "2026-10"
_LOCK = threading.RLock()
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")

# a step's video may come only from these hosts, as an embed URL; the page shows a click-to-load facade (nothing loads until the learner asks)
VIDEO_HOSTS = {"www.youtube-nocookie.com": "/embed/", "player.vimeo.com": "/video/", "www.facebook.com": "/plugins/video.php"}

_context = [lambda: {"profile": {}, "posts": [], "vault": []}]


def set_context_provider(fn):
    """platform_mode tells the academy how to look at what the learner really did (profile, posts, vault) so that checks are made against facts."""
    _context[0] = fn


AUTO_CHECKS = {
    "profile_complete": ("name, headline and About are filled in", lambda c: all((c["profile"].get(k) or "").strip() for k in ("name", "headline", "about"))),
    "first_post": ("you have posted on the floor", lambda c: len(c["posts"]) >= 1),
    "public_post": ("you have a public post", lambda c: any(p.get("public") for p in c["posts"])),
    "public_post_substantial": ("you have a public post of at least 40 characters", lambda c: any(p.get("public") and len((p.get("text") or "").strip()) >= 40 for p in c["posts"])),
    "profile_photo": ("you chose a profile photo", lambda c: bool(c["profile"].get("avatar"))),
    "first_photo": ("you have a photo in your vault", lambda c: len(c["vault"]) >= 1),
    "featured_post": ("you featured a post on your profile wall", lambda c: len(c["profile"].get("featured") or []) >= 1),
}


# ---------------------------------------------------------------- the curriculum
def _valid_video(v):
    if v is None:
        return None
    if not isinstance(v, dict):
        return None
    try:
        u = urllib.parse.urlsplit(str(v.get("url", "")))
    except ValueError:
        return None
    if u.scheme != "https" or u.hostname not in VIDEO_HOSTS or not u.path.startswith(VIDEO_HOSTS[u.hostname]) or len(u.geturl()) > 400:
        return None
    return {"title": str(v.get("title", "Video"))[:120], "url": u.geturl(), "host": u.hostname, "credit": str(v.get("credit", ""))[:120]}


def load_curriculum():
    """-> (tracks, problems). Every file is validated; a bad step is reported, never silently shown."""
    tracks, problems, seen = [], [], set()
    for path in sorted(glob.glob(os.path.join(CURRICULUM_DIR, "*.json"))):
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as f:
                tr = json.load(f)
        except (OSError, ValueError) as e:
            problems.append("%s: cannot read (%s)" % (name, type(e).__name__))
            continue
        if not isinstance(tr, dict) or not _SLUG.match(str(tr.get("id", ""))) or tr["id"] in seen or not tr.get("modules"):
            problems.append("%s: needs a unique slug id and modules" % name)
            continue
        seen.add(tr["id"])
        ids = set()
        for m in tr["modules"]:
            if not _SLUG.match(str(m.get("id", ""))) or not m.get("steps"):
                problems.append("%s: module %r needs an id and steps" % (name, m.get("id")))
            for s in m.get("steps", []):
                key = (m.get("id"), s.get("id"))
                proof = s.get("proof", "")
                if not _SLUG.match(str(s.get("id", ""))) or key in ids:
                    problems.append("%s: bad or duplicate step id %r" % (name, s.get("id")))
                ids.add(key)
                if not (proof in ("note", "link") or (proof.startswith("auto:") and proof[5:] in AUTO_CHECKS)):
                    problems.append("%s: step %r has an unknown proof %r" % (name, s.get("id"), proof))
                if s.get("video") and not _valid_video(s["video"]):
                    problems.append("%s: step %r has a video from a host that is not allowed" % (name, s.get("id")))
                s["video"] = _valid_video(s.get("video"))
                for k in ("title", "why", "check"):
                    if not str(s.get(k, "")).strip():
                        problems.append("%s: step %r is missing %s" % (name, s.get("id"), k))
        tracks.append(tr)
    return tracks, problems


def _find(tracks, track_id, step_id=None):
    tr = next((t for t in tracks if t["id"] == track_id), None)
    if not tr or step_id is None:
        return tr, None, None
    for m in tr["modules"]:
        for s in m["steps"]:
            if s["id"] == step_id:
                return tr, m, s
    return tr, None, None


# ---------------------------------------------------------------- progress
def _read():
    try:
        with open(PROGRESS_PATH, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("state", {})
            d.setdefault("done", {})
            return d
    except (OSError, ValueError):
        pass
    return {"state": {}, "done": {}}


def _write(d):
    os.makedirs(os.path.dirname(PROGRESS_PATH), exist_ok=True)
    tmp = PROGRESS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, PROGRESS_PATH)


def _ledger():
    out = []
    try:
        with open(BADGES_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _step_done(done, track_id, step_id):
    return "%s/%s" % (track_id, step_id) in done


def badge_definitions(tracks):
    defs = []
    for tr in tracks:
        for m in tr["modules"]:
            defs.append({"id": "%s:%s" % (tr["id"], m["id"]), "name": m.get("badge") or m["title"], "kind": "module", "track": tr["id"],
                         "criteria": "Finish every step in the module \"%s\" (%d steps)." % (m["title"], len(m["steps"]))})
        defs.append({"id": tr["id"], "name": tr.get("badge") or tr["title"], "kind": "track", "track": tr["id"],
                     "criteria": "Finish every module in the track \"%s\"." % tr["title"]})
    defs.append({"id": "mentor-ready", "name": "Mentor-ready", "kind": "leadership", "track": None,
                 "criteria": "Finish any whole track. This is the first step of the leadership loop: you can now guide others through it. Mentoring itself needs other people on the platform and is not built yet."})
    return defs


def _evidence_level(done, track, module_ids=None):
    kinds = []
    for m in track["modules"]:
        if module_ids is not None and m["id"] not in module_ids:
            continue
        for s in m["steps"]:
            d = done.get("%s/%s" % (track["id"], s["id"]))
            kinds.append("verified" if d and d.get("proof") == "auto" else "self-reported")
    if kinds and all(k == "verified" for k in kinds):
        return "verified"
    if kinds and all(k == "self-reported" for k in kinds):
        return "self-reported"
    return "mixed"


def _award(tracks, done):
    have = {b["badge"] for b in _ledger()}
    new = []
    track_complete = False
    for tr in tracks:
        mods_done = []
        for m in tr["modules"]:
            if all(_step_done(done, tr["id"], s["id"]) for s in m["steps"]):
                mods_done.append(m["id"])
                bid = "%s:%s" % (tr["id"], m["id"])
                if bid not in have:
                    new.append({"badge": bid, "name": m.get("badge") or m["title"], "kind": "module", "evidence": _evidence_level(done, tr, {m["id"]}), "steps": len(m["steps"])})
        if len(mods_done) == len(tr["modules"]):
            track_complete = True
            if tr["id"] not in have:
                new.append({"badge": tr["id"], "name": tr.get("badge") or tr["title"], "kind": "track", "evidence": _evidence_level(done, tr), "steps": sum(len(m["steps"]) for m in tr["modules"])})
    if track_complete and "mentor-ready" not in have:
        new.append({"badge": "mentor-ready", "name": "Mentor-ready", "kind": "leadership", "evidence": "earned by finishing a track", "steps": 0})
    if new:
        os.makedirs(os.path.dirname(BADGES_PATH), exist_ok=True)
        now = int(time.time())
        with open(BADGES_PATH, "a", encoding="utf-8") as f:
            for b in new:
                b["t"] = now
                f.write(json.dumps(b) + "\n")
    return new


class AcademyError(ValueError):
    pass


def complete_step(track_id, step_id, evidence=""):
    """Mark a step done. Auto steps are checked against what you really did and cannot be marked otherwise; others need a short note or a link. -> {"step", "new_badges"}."""
    tracks, _ = load_curriculum()
    tr, m, s = _find(tracks, str(track_id), str(step_id))
    if not s:
        raise AcademyError("No such step.")
    key = "%s/%s" % (tr["id"], s["id"])
    evidence = str(evidence or "").strip()
    with _LOCK:
        data = _read()
        if key in data["done"]:
            return {"step": dict(data["done"][key], id=s["id"]), "new_badges": []}
        proof = s["proof"]
        if proof.startswith("auto:"):
            label, check = AUTO_CHECKS[proof[5:]]
            if not check(_context[0]()):
                raise AcademyError("Not yet: %s. NEXXUS checks this itself, so it cannot be ticked by hand." % label)
            rec = {"t": int(time.time()), "proof": "auto", "evidence": label}
        elif proof == "link":
            u = urllib.parse.urlsplit(evidence)
            if u.scheme != "https" or not u.hostname or len(evidence) > 300:
                raise AcademyError("Add the https link that shows what you did.")
            rec = {"t": int(time.time()), "proof": "link", "evidence": evidence}
        else:
            if len(evidence) < 10:
                raise AcademyError("Write a sentence or two about what you did (at least 10 characters). It is self-reported: NEXXUS cannot check it, and the badge will say so.")
            rec = {"t": int(time.time()), "proof": "note", "evidence": evidence[:300]}
        data["done"][key] = rec
        _write(data)
        new = _award(tracks, data["done"])
    return {"step": dict(rec, id=s["id"]), "new_badges": new}


def _public(step, data, track_id):
    d = data["done"].get("%s/%s" % (track_id, step["id"]))
    return {"id": step["id"], "title": step["title"], "done": bool(d), "proof": step["proof"], "auto": step["proof"].startswith("auto:"), "completed": d}


def track_detail(track_id):
    tracks, _ = load_curriculum()
    tr = next((t for t in tracks if t["id"] == track_id), None)
    if not tr:
        return None
    data = _read()
    out = dict(tr, modules=[])
    for m in tr["modules"]:
        steps = []
        for s in m["steps"]:
            d = data["done"].get("%s/%s" % (tr["id"], s["id"]))
            full = dict(s, done=bool(d), completed=d)
            if s["proof"].startswith("auto:"):
                full["auto_text"] = AUTO_CHECKS[s["proof"][5:]][0]
            steps.append(full)
        out["modules"].append(dict(m, steps=steps))
    return out


# ---------------------------------------------------------------- onboarding
def set_path(path, track=None):
    if path not in ("solo", "group"):
        raise AcademyError("Choose Solo Build or Group Build.")
    tracks, _ = load_curriculum()
    if track is not None and not any(t["id"] == track for t in tracks):
        raise AcademyError("No such track.")
    with _LOCK:
        d = _read()
        d["state"].update(path=path, track=track, chosen=int(time.time()))
        _write(d)
    return d["state"]


def acknowledge_conduct():
    with _LOCK:
        d = _read()
        d["state"]["conduct"] = {"version": CONDUCT_VERSION, "t": int(time.time())}
        _write(d)
    return d["state"]["conduct"]


def quests():
    """Onboarding quests. The ones NEXXUS can check itself are checked against what you really did; the ones that need other people say so and stay open."""
    ctx, st = _context[0](), _read()["state"]
    return [
        {"id": "conduct", "title": "Read and accept the Code of Conduct (PG-13, respect, privacy)", "done": (st.get("conduct") or {}).get("version") == CONDUCT_VERSION, "how": "tick the box", "available": True},
        {"id": "profile", "title": "Fill in your profile: name, headline and About", "done": AUTO_CHECKS["profile_complete"][1](ctx), "how": "checked by NEXXUS", "available": True},
        {"id": "intro", "title": "Post an introduction on the floor", "done": AUTO_CHECKS["first_post"][1](ctx), "how": "checked by NEXXUS", "available": True},
        {"id": "public", "title": "Share a post publicly", "done": AUTO_CHECKS["public_post"][1](ctx), "how": "checked by NEXXUS", "available": True},
        {"id": "path", "title": "Choose your path: Solo Build or Group Build", "done": bool(st.get("path")), "how": "your choice", "available": True},
        {"id": "peers", "title": "Connect with your first peers", "done": False, "how": "needs other people on the platform", "available": False},
        {"id": "review", "title": "Review a peer's project", "done": False, "how": "needs other people on the platform", "available": False},
    ]


def group_checklist():
    """The Group Build trust protocol. Entry to a team pod is earned through real interaction with real people, so most steps wait for the network."""
    ctx = _context[0]()
    items = [
        {"id": "intro", "title": "Introduce yourself on the floor", "done": AUTO_CHECKS["public_post"][1](ctx), "available": True, "how": "checked by NEXXUS"},
        {"id": "interact", "title": "Comment helpfully on other people's public posts", "done": False, "available": False, "how": "needs other people on the platform"},
        {"id": "collaborate", "title": "Collaborate with a peer on a small task", "done": False, "available": False, "how": "needs other people on the platform"},
        {"id": "relationship", "title": "Build a relationship: a peer vouches for working with you", "done": False, "available": False, "how": "needs other people on the platform"},
    ]
    return {"items": items, "pod_entry": "locked", "note": "Team pods open once these steps are done with real people. Pods are not built yet, so nothing here is faked."}


def welcome():
    """The orientation shown when someone first enters Platform mode (and from the "What is this?" button). It separates what works today from what is planned, so nobody is promised
    something that does not exist. test_academy.py checks that every planned item is marked not available."""
    return {
        "title": "Welcome to NEXXUS Platform",
        "what": "NEXXUS Platform is a sovereign digital academy, a collaborative workspace and a company-building ground. You learn to build, operate and run real systems with exact prompts and commands, "
                "earn badges as proof of what you learned and did, and then lead others through the same path.",
        "beta": {"headline": "BETA: wide open",
                 "text": "Right now everything that exists is open to everyone, free, with no purchase and no locked tiers. You are at the ground floor: explore, test and build across the whole platform while it is "
                         "being built. Before the public launch some tiers may be introduced. If that happens you will see exactly what each one includes before you pay. Nobody is charged during Beta."},
        "today": [
            {"title": "The Academy", "text": "Four tracks, 24 steps with exact prompts and commands, and badges that record how they were proved."},
            {"title": "Your profile wall", "text": "A LinkedIn-style page with a visitor preview, section by section privacy and an image vault."},
            {"title": "The floor and public wall", "text": "Posts with photos, comments and ratings, live across your open windows, plus a public wall with a GitHub audit trail."},
            {"title": "Talk to NEXXUS", "text": "A private line to the local NEXXUS for questions, debugging and guidance. Never posted, never public."},
            {"title": "Transparent ranks", "text": "One readable ledger of public contributions is the whole formula. Nothing is hidden."},
            {"title": "Team workspaces", "text": "A task board, Academy blueprints, a control center and real system telemetry for your team, pod or company. Today a workspace has one member, you."},
            {"title": "Private by design", "text": "Direct messages, group chats and live rooms are never collected, never public, never synced to GitHub and never counted for ranks."},
        ],
        "planned": [
            {"title": "Teams across the country", "needs": "a shared network with accounts and moderation", "text": "Invite other builders, form real teams and companies together."},
            {"title": "Live clustered rooms", "needs": "other people on a shared server", "text": "Group video and voice rooms inside team workspaces."},
            {"title": "Developer pods", "needs": "other people and the trust protocol", "text": "Team pods you can join after the Group Build trust steps."},
            {"title": "Business telephony", "needs": "a telephony provider account, a number and legal registration", "text": "A real company phone line."},
            {"title": "Team automation bots and storefront connections", "needs": "integration work not yet built", "text": "Bots that run your team's tasks and storefronts managed from the workspace."},
        ],
        "planned_label": "Not available yet",
        "terms": terms(), "terms_accepted": terms_accepted(),
        "privacy": "Your private conversations stay private.",
    }


TERMS_VERSION = "alpha-1"
TERMS_TITLE = "Platform Alpha: Terms of Engagement"
TERMS = [
    {"title": "1. Solo freedom",
     "text": "Working as an individual builder, you are free to create, manage and scale multiple companies, projects and portals within your account. Nothing here limits your individual hustle.",
     "today": "A local workspace limit of %d applies today (it protects the files on your computer, not your ambition)." % 10},
    {"title": "2. Team collaboration and active clustering",
     "text": "Partnerships on Platform Alpha are built on real, verified contribution. If you form a team or collaborate with others, your accounts formally cluster within the system. Real collaboration requires active "
             "synchronization: passive passengers and uncommitted participants are not maintained within active team structures. If you are not clustering and building with your unit, you are not on the team.",
     "today": "Teams across accounts are not built yet; a workspace has one member, you. No one can be removed for inactivity because nothing measures it yet. When teams exist, the contribution rule will be shown here first."},
]
TERMS_CLOSING = "By activating your account and entering Platform Alpha, you agree to uphold these standards of real-world value, accountability and mutual growth."


def terms():
    """The terms shown at onboarding, with a hash of the exact text so an acceptance is tied to the words that were on screen."""
    body = json.dumps([TERMS_VERSION, TERMS_TITLE, TERMS, TERMS_CLOSING], sort_keys=True)
    return {"version": TERMS_VERSION, "title": TERMS_TITLE, "sections": TERMS, "closing": TERMS_CLOSING, "sha256": hashlib.sha256(body.encode()).hexdigest()}


def accept_terms(version):
    """Record that this person agreed to the current terms (a stale or unknown version is refused, so an old screen cannot accept new words). -> the acceptance record."""
    t = terms()
    if version != t["version"]:
        raise ValueError("These terms changed. Reload and read the current version.")
    with _LOCK:
        d = _read()
        d["state"]["terms"] = {"version": t["version"], "sha256": t["sha256"], "t": int(time.time())}
        _write(d)
    return d["state"]["terms"]


def terms_accepted():
    rec = _read()["state"].get("terms")
    return bool(rec) and rec.get("sha256") == terms()["sha256"]


def mark_welcomed():
    with _LOCK:
        d = _read()
        d["state"]["welcomed"] = int(time.time())
        _write(d)
    return d["state"]["welcomed"]


def overview():
    tracks, problems = load_curriculum()
    data = _read()
    badges = _ledger()
    out_tracks = []
    for tr in tracks:
        steps = [s for m in tr["modules"] for s in m["steps"]]
        done = sum(1 for s in steps if _step_done(data["done"], tr["id"], s["id"]))
        out_tracks.append({"id": tr["id"], "title": tr["title"], "badge": tr.get("badge"), "summary": tr.get("summary", ""), "audience": tr.get("audience", ""),
                           "disclaimer": tr.get("disclaimer", ""), "steps": len(steps), "done": done,
                           "modules": [{"id": m["id"], "title": m["title"], "badge": m.get("badge"), "goal": m.get("goal", ""),
                                        "steps": [_public(s, data, tr["id"]) for s in m["steps"]]} for m in tr["modules"]]})
    earned = {b["badge"] for b in badges}
    defs = [dict(d, earned=d["id"] in earned, earned_info=next((b for b in badges if b["badge"] == d["id"]), None)) for d in badge_definitions(tracks)]
    return {"state": data["state"], "welcome": welcome(), "tracks": out_tracks, "badges": defs, "problems": problems, "quests": quests(), "group": group_checklist(),
            "leadership": {"mentor_ready": "mentor-ready" in earned,
                           "text": "The leadership loop: work through the system, master the tools, then guide others through the same path. Finish a whole track to become Mentor-ready. Mentoring itself needs other people on the platform and is not built yet."},
            "beta": "Open Beta: every track is open from day one. No payment, no prerequisites."}
