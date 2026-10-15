"""teams.py - team and pod workspaces: the foundation for forming a company inside Platform mode.

A team (or pod, or company) has a mission, members with roles, a task board, Academy blueprints attached to it, an activity log and a leader's control center. Everything here is REAL and LOCAL:
the board, the progress, the blueprint progress (read from the Academy), the activity log and the system telemetry (read from this NEXXUS: its engines and hub, never invented).

What it cannot do yet, and says so: invite other people (that needs the network), run team video rooms, or connect a company phone line. Those appear in the control center as "not available yet",
each with the reason, never as a working-looking placeholder. Team workspaces are private to the person who made them; nothing here is public or synced to GitHub.
"""
import json
import os
import re
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
TEAMS_PATH = os.path.join(HERE, "nexxus_data", "platform", "teams.json")
KINDS = ("team", "pod", "company")
STATUSES = ("todo", "doing", "done")
MAX_TEAMS = 10
MAX_TASKS = 200
MAX_ACTIVITY = 200
_LOCK = threading.RLock()
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_providers = {"tracks": lambda: [], "system": lambda: None}


def set_providers(tracks=None, system=None):
    """platform_mode / the server tell this module how to read Academy progress and system telemetry."""
    if tracks:
        _providers["tracks"] = tracks
    if system:
        _providers["system"] = system


class TeamError(ValueError):
    pass


def _clean(s, n):
    return _CTRL.sub("", str(s or "")).strip()[:n]


def _read():
    try:
        with open(TEAMS_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _write(teams):
    os.makedirs(os.path.dirname(TEAMS_PATH), exist_ok=True)
    tmp = TEAMS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(teams, f)
    os.replace(tmp, TEAMS_PATH)


def _log(team, kind, text):
    team["activity"].append({"t": int(time.time()), "type": kind, "text": _clean(text, 160)})
    del team["activity"][:-MAX_ACTIVITY]


def _find(teams, tid):
    t = next((x for x in teams if x["id"] == str(tid)), None)
    if not t:
        raise TeamError("No such team.")
    return t


def create_team(name, mission="", kind="team", leader_name="You"):
    name = _clean(name, 60)
    if not name:
        raise TeamError("Give the team a name.")
    if kind not in KINDS:
        raise TeamError("A workspace is a team, a pod or a company.")
    with _LOCK:
        teams = _read()
        if len(teams) >= MAX_TEAMS:
            raise TeamError("That is the limit of %d workspaces." % MAX_TEAMS)
        t = {"id": uuid.uuid4().hex[:10], "name": name, "mission": _clean(mission, 200), "kind": kind, "created": int(time.time()),
             "members": [{"id": "you", "name": _clean(leader_name, 40) or "You", "role": "leader"}], "tracks": [], "tasks": [], "activity": []}
        _log(t, "team", "Workspace created.")
        teams.append(t)
        _write(teams)
        return t


def delete_team(tid):
    with _LOCK:
        teams = _read()
        _find(teams, tid)
        _write([x for x in teams if x["id"] != str(tid)])


def add_task(tid, title, detail="", due="", assignee="you"):
    title = _clean(title, 120)
    if not title:
        raise TeamError("A task needs a title.")
    due = due if _DATE.match(str(due or "")) else ""
    with _LOCK:
        teams = _read()
        t = _find(teams, tid)
        if len(t["tasks"]) >= MAX_TASKS:
            raise TeamError("This board is full (%d tasks)." % MAX_TASKS)
        if assignee not in {m["id"] for m in t["members"]}:
            assignee = "you"
        task = {"id": uuid.uuid4().hex[:8], "title": title, "detail": _clean(detail, 500), "status": "todo", "assignee": assignee, "due": due, "created": int(time.time()), "done_t": 0}
        t["tasks"].append(task)
        _log(t, "task", "Task added: " + title)
        _write(teams)
        return task


def move_task(tid, task_id, status):
    if status not in STATUSES:
        raise TeamError("A task is to do, doing or done.")
    with _LOCK:
        teams = _read()
        t = _find(teams, tid)
        task = next((x for x in t["tasks"] if x["id"] == str(task_id)), None)
        if not task:
            raise TeamError("No such task.")
        if task["status"] != status:
            task["status"] = status
            task["done_t"] = int(time.time()) if status == "done" else 0
            _log(t, "task", ("Task done: " if status == "done" else "Task moved to %s: " % status) + task["title"])
            _write(teams)
        return task


def delete_task(tid, task_id):
    with _LOCK:
        teams = _read()
        t = _find(teams, tid)
        before = len(t["tasks"])
        t["tasks"] = [x for x in t["tasks"] if x["id"] != str(task_id)]
        if len(t["tasks"]) == before:
            raise TeamError("No such task.")
        _log(t, "task", "Task removed.")
        _write(teams)


def attach_track(tid, track_id, on=True):
    known = {tr["id"] for tr in _providers["tracks"]()}
    if track_id not in known:
        raise TeamError("No such Academy track.")
    with _LOCK:
        teams = _read()
        t = _find(teams, tid)
        if on and track_id not in t["tracks"]:
            t["tracks"].append(track_id)
            _log(t, "blueprint", "Blueprint attached: " + track_id)
        elif not on and track_id in t["tracks"]:
            t["tracks"].remove(track_id)
            _log(t, "blueprint", "Blueprint removed: " + track_id)
        _write(teams)
        return t["tracks"]


def _system_summary():
    """Real telemetry from this NEXXUS, or None if it cannot be read. Never invented."""
    try:
        raw = _providers["system"]()
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    engines = raw.get("engines") or {}
    hub = raw.get("hub") or {}
    return {"engines_total": len(engines), "engines_found": sum(1 for e in engines.values() if e.get("found")), "engines_mesh_ready": sum(1 for e in engines.values() if e.get("mesh_ready")),
            "engines": sorted(({"name": n, "found": bool(e.get("found")), "mesh_ready": bool(e.get("mesh_ready"))} for n, e in engines.items()), key=lambda x: x["name"]),
            "hub": {k: hub[k] for k in ("uptime_s", "cpu_percent", "rss_mb", "threads") if k in hub}}


def _blueprints(team):
    out = []
    for tr in _providers["tracks"]():
        if tr["id"] in team["tracks"]:
            out.append({"id": tr["id"], "title": tr["title"], "badge": tr.get("badge"), "steps": tr["steps"], "done": tr["done"], "percent": round(100 * tr["done"] / max(1, tr["steps"]))})
    return out


def company_stack(team):
    """The business tools a company needs, with their TRUE status. Nothing is shown as connected unless it is."""
    return [
        {"id": "storefront", "name": "Storefront", "status": "learn", "text": "The Academy's Digital storefront track teaches the whole path. Connecting a live storefront to a team workspace is not built yet."},
        {"id": "bots", "name": "Automation bots", "status": "system", "text": "NEXXUS's own engines are the automation layer and are shown live above. Team-specific bots that run your company's tasks are not built yet."},
        {"id": "phone", "name": "Company phone line", "status": "unavailable", "text": "Not available. A real phone line needs an account with a telephony provider, a number, identity checks and legal registration. NEXXUS does not provide or fake one."},
        {"id": "rooms", "name": "Team video and voice rooms", "status": "unavailable", "text": "Not available yet. Live rooms need other people connected to a shared server, which does not exist yet."},
        {"id": "invites", "name": "Inviting teammates", "status": "unavailable", "text": "Not available yet. Members join through the network, which is not built; today a workspace has one member, you."},
    ]


def dashboard(team):
    now = time.time()
    tasks = team["tasks"]
    counts = {s: sum(1 for x in tasks if x["status"] == s) for s in STATUSES}
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    overdue = [x for x in tasks if x["status"] != "done" and x["due"] and x["due"] < today]
    total = len(tasks)
    pct = round(100 * counts["done"] / total) if total else 0
    if not total:
        health = "empty"
    elif overdue:
        health = "behind"
    elif counts["doing"] or counts["done"]:
        health = "moving"
    else:
        health = "not started"
    week = now - 7 * 86400
    return {"counts": counts, "total": total, "percent": pct, "overdue": [{"id": x["id"], "title": x["title"], "due": x["due"]} for x in overdue], "health": health,
            "done_this_week": sum(1 for x in tasks if x["status"] == "done" and x["done_t"] >= week), "blueprints": _blueprints(team),
            "activity": list(reversed(team["activity"]))[:20], "system": _system_summary(),
            "channels": {"available": False, "text": "No communication channels yet: team chat and live rooms need the network, which is not built."},
            "stack": company_stack(team)}


def list_teams():
    return [{"id": t["id"], "name": t["name"], "kind": t["kind"], "mission": t["mission"], "members": len(t["members"]), "tasks": len(t["tasks"]),
             "done": sum(1 for x in t["tasks"] if x["status"] == "done")} for t in _read()]


def get_team(tid):
    t = _find(_read(), tid)
    return dict(t, dashboard=dashboard(t))
