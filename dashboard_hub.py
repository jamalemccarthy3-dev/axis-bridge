"""dashboard_hub.py - the Academy workspace: your dashboards and bot setups, with a disciplined number of active slots, a Work Safe vault and a real delete.

    Active rotation   at most MAX_ACTIVE (10) dashboards and MAX_ACTIVE (10) bot setups are active at once. Focus is the point: a full rotation asks you to rest something or delete it.
    Work Safe vault   a resting dashboard or bot setup is kept intact (its name, note and configuration) and takes no active slot. Restoring it needs a free slot.
    Purge             deleting is permanent: the record and its configuration are removed from this computer's store. Copies you exported or shared elsewhere are not touched.

What this is NOT: a limit on what you build on your own NEXXUS. The slots count Academy workspace records only; the NEXXUS engines, factory and builds on your node are unconstrained and never ask this module for
permission. A record can name the local engine it belongs to (checked against the engines your NEXXUS really reports), which is the link back to your node. A record is private unless you mark it public, and
only then do its name, kind and engine appear on your visitor profile.
"""
import json
import os
import re
import tempfile
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(HERE, "nexxus_data", "platform", "hub.json")
KINDS = ("dashboard", "bot")
MAX_ACTIVE = 10
MAX_SAFE = 100            # per kind; the vault is generous but not unbounded
MAX_CONFIG = 4000         # bytes of JSON configuration kept per record
_LOCK = threading.RLock()
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_engines = [lambda: None]       # platform_mode installs a function that returns the engine names this NEXXUS really reports


class HubError(ValueError):
    pass


def set_engine_provider(fn):
    _engines[0] = fn


def _clean(s, n):
    return _CTRL.sub("", str(s or "")).strip()[:n]


def _read():
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _write(items):
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STORE_PATH), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(items, f)
    os.replace(tmp, STORE_PATH)


def _count(items, kind, state):
    return sum(1 for x in items if x["kind"] == kind and x["state"] == state)


def _find(items, hid):
    for x in items:
        if x["id"] == str(hid):
            return x
    raise HubError("No such item.")


def _engine(name):
    name = _clean(name, 60)
    if not name:
        return ""
    known = _engines[0]()
    if known is None or name not in known:
        raise HubError("That is not an engine this NEXXUS reports. Leave it blank or pick one from the list.")
    return name


def _config(c):
    if c in (None, ""):
        return {}
    if not isinstance(c, dict):
        raise HubError("The configuration must be a JSON object.")
    if len(json.dumps(c)) > MAX_CONFIG:
        raise HubError("The configuration is larger than %d characters." % MAX_CONFIG)
    return c


def slots():
    items = _read()
    return {k: {"active": _count(items, k, "active"), "max": MAX_ACTIVE, "safe": _count(items, k, "safe"), "safe_max": MAX_SAFE} for k in KINDS}


def snapshot():
    items = _read()
    return {"items": sorted(items, key=lambda x: x["updated"], reverse=True), "slots": slots(), "engines": sorted(_engines[0]() or []),
            "rules": ["Up to %d active dashboards and %d active bot setups at a time." % (MAX_ACTIVE, MAX_ACTIVE),
                      "Resting work goes to the Work Safe vault and is kept intact.",
                      "Purging is permanent and removes it from this computer. Anything you exported or shared elsewhere is not touched.",
                      "These slots count Academy workspace records only. What you build on your own NEXXUS is never limited by them."]}


def create(kind, name, note="", engine="", config=None, public=False):
    if kind not in KINDS:
        raise HubError("A hub item is a dashboard or a bot setup.")
    name = _clean(name, 60)
    if not name:
        raise HubError("Give it a name.")
    eng, cfg = _engine(engine), _config(config)
    with _LOCK:
        items = _read()
        if _count(items, kind, "active") >= MAX_ACTIVE:
            raise HubError("All %d active %s slots are in use. Move one to the Work Safe vault, or delete one, to make room." % (MAX_ACTIVE, kind))
        now = int(time.time())
        item = {"id": uuid.uuid4().hex[:10], "kind": kind, "name": name, "note": _clean(note, 300), "engine": eng, "config": cfg, "public": bool(public), "state": "active", "created": now, "updated": now}
        items.append(item)
        _write(items)
    return item


def update(hid, name=None, note=None, engine=None, config=None, public=None):
    with _LOCK:
        items = _read()
        x = _find(items, hid)
        if name is not None:
            n = _clean(name, 60)
            if not n:
                raise HubError("Give it a name.")
            x["name"] = n
        if note is not None:
            x["note"] = _clean(note, 300)
        if engine is not None:
            x["engine"] = _engine(engine)
        if config is not None:
            x["config"] = _config(config)
        if public is not None:
            x["public"] = bool(public)
        x["updated"] = int(time.time())
        _write(items)
        return x


def shelve(hid):
    """Move to the Work Safe vault: nothing is lost, the slot is freed, and it is never shown publicly while resting."""
    with _LOCK:
        items = _read()
        x = _find(items, hid)
        if x["state"] == "safe":
            return x
        if _count(items, x["kind"], "safe") >= MAX_SAFE:
            raise HubError("The Work Safe vault is full (%d). Delete something you no longer need." % MAX_SAFE)
        x["state"], x["updated"] = "safe", int(time.time())
        _write(items)
        return x


def restore(hid):
    with _LOCK:
        items = _read()
        x = _find(items, hid)
        if x["state"] == "active":
            return x
        if _count(items, x["kind"], "active") >= MAX_ACTIVE:
            raise HubError("All %d active %s slots are in use. Rest or delete another first." % (MAX_ACTIVE, x["kind"]))
        x["state"], x["updated"] = "active", int(time.time())
        _write(items)
        return x


def purge(hid, confirm_name):
    """Permanent deletion. The exact name must be typed back so a stray click cannot destroy work."""
    with _LOCK:
        items = _read()
        x = _find(items, hid)
        if _clean(confirm_name, 60) != x["name"]:
            raise HubError("To delete it for good, type its exact name: %s" % x["name"])
        _write([i for i in items if i["id"] != x["id"]])
    return {"purged": x["id"], "name": x["name"]}


def public_items():
    """What a visitor may see: only active items you marked public, with name, kind and engine. Notes and configuration are never included."""
    return [{"name": x["name"], "kind": x["kind"], "engine": x["engine"]} for x in _read() if x["public"] and x["state"] == "active"]
