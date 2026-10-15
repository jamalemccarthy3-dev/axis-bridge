"""portals.py - the NEXXUS data bridge for the four command-deck portals: Sports, Markets, Logistics, Economics.

The portals in the dashboard are visual controllers only. Every calculation runs in axis-logic (silo_vault/axis-logic/portal_worker.py) in a throwaway
subprocess with a time limit, so the heavy maths and the engines stay on the backend and a bad input can never take the server down.

Data: this module invents nothing and ships no data. The portals read the owner's own files in portal_data/ (ticker, players, teams, legs, series, assets, macro), each checked against the
schema in portal_schemas.py (provenance required; sample, placeholder, demo or mock data is rejected). A missing file is "not loaded" and is reported as exactly that, to the page and to every hub's
prompt. Nothing here places a bet, trades, orders or ships anything.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import portal_schemas

HERE = Path(__file__).resolve().parent
WORKER = HERE / "axis-ui-interface" / "project-X" / "silo_vault" / "axis-logic" / "portal_worker.py"
DATA_DIR = Path(os.environ.get("NEXXUS_PORTAL_DATA") or (HERE / "portal_data"))
TIMEOUT_S = 25
MAX_BODY = 262144

ORDER = ("sports", "markets", "logistics", "economics")      # the dock order, left of Home -> Link -> Build
CATALOG = {
    "sports": {"title": "Sports", "icon": "S", "tabs": ["Broadcast", "Players", "Teams", "Parlay"], "ops": ["sports.evaluate", "sports.compare", "sports.player", "sports.parlay"], "data": ["ticker", "players", "teams", "legs"]},
    "markets": {"title": "Markets", "icon": "M", "tabs": ["Probability", "Forecast"], "ops": ["markets.analyze", "markets.forecast"], "data": ["series"]},
    "logistics": {"title": "Logistics", "icon": "L", "tabs": ["Cockpit", "Inventory", "Queue", "Delivery"], "ops": ["logistics.stockout", "logistics.queue", "logistics.eoq", "logistics.reorder", "logistics.ontime", "logistics.fulfillment_test"], "data": ["assets"]},
    "economics": {"title": "Economics", "icon": "E", "tabs": ["Macro", "Modeling"], "ops": ["economics.model"], "data": ["macro"]},
}
ALL_OPS = tuple(op for c in CATALOG.values() for op in c["ops"]) + ("hub.search",)
MAX_MOUNTED = 40
HUB_CATALOG = "hub_catalog"


class PortalError(Exception):
    pass


class PortalBusy(PortalError):
    """Three calculations are already running; the caller should retry in a moment."""


_SLOTS = threading.BoundedSemaphore(3)


def available():
    return WORKER.is_file()


def _read_json(name):
    p = DATA_DIR / (name + ".json")
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"error": "%s.json could not be read as JSON" % name}


def _data_names():
    return {n for c in CATALOG.values() for n in c["data"]}


def data(name):
    """One data set, as it really is. -> {"missing": True, "schema"} when there is no file, {"invalid": True, "errors", "schema"} when the file breaks its schema or calls itself sample or
    placeholder data (nothing from it is used), else the file's own content plus {"row_count"}. Nothing is ever filled in."""
    if name not in _data_names():
        raise PortalError("unknown data set %r" % name)
    d = _read_json(name)
    schema = portal_schemas.describe(name)
    if d is None:
        return {"missing": True, "name": name, "path": "portal_data/%s.json" % name, "schema": schema}
    errs = [d["error"]] if isinstance(d, dict) and set(d) == {"error"} else portal_schemas.validate(name, d)
    if errs:
        return {"invalid": True, "name": name, "path": "portal_data/%s.json" % name, "errors": errs, "schema": schema}
    return dict(d, **portal_schemas.summary(name, d), name=name)


def save_data(name, doc):
    """Validate and store the owner's data set (atomic write). Raises PortalError listing every problem; nothing is written unless the whole file is valid."""
    if name not in _data_names():
        raise PortalError("unknown data set %r" % name)
    errs = portal_schemas.validate(name, doc)
    if errs:
        raise PortalError("not saved: " + "; ".join(errs))
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if len(text.encode("utf-8")) > 4_000_000:
        raise PortalError("not saved: the file is larger than 4 MB")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = DATA_DIR / (name + ".json")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)
    return dict(portal_schemas.summary(name, doc), name=name, source=doc["source"])


def state(domain):
    """The live state of one hub, read from the system right now: what data is loaded (with provenance), what is not, the calculators and their exact arguments, the catalog size and what the owner
    added to the hub. This is what every hub prompt carries, so the models never have to guess what exists."""
    if domain not in CATALOG:
        raise PortalError("unknown portal %r" % domain)
    sets = []
    for n in CATALOG[domain]["data"]:
        d = data(n)
        sets.append({"name": n, "status": "missing" if d.get("missing") else "invalid" if d.get("invalid") else "loaded", "row_count": d.get("row_count"), "source": d.get("source"), "errors": d.get("errors", [])[:3]})
    return {"domain": domain, "data": sets, "ops": [{"op": o, "args": portal_schemas.OP_ARGS[o]} for o in CATALOG[domain]["ops"]], "catalog_entries": len(hub_entries(domain)),
            "mounted": [e["name"] for e in hub_mounted(domain)]}


def catalog():
    out = {"status": "success", "order": list(ORDER), "available": available(), "hub": hub_meta(), "chat": {"web_search": os.environ.get("NEXXUS_PORTAL_WEB_SEARCH", "1") != "0"}, "portals": {}, "no_execution": "Estimates with their uncertainty only. No bet, trade, order or shipment is ever placed from here."}
    for k in ORDER:
        c = CATALOG[k]
        sets = {}
        for n in c["data"]:
            d = data(n)
            sets[n] = {"status": "missing" if d.get("missing") else "invalid" if d.get("invalid") else "loaded", "row_count": d.get("row_count"), "source": d.get("source"), "errors": d.get("errors", [])[:3]}
        out["portals"][k] = {"title": c["title"], "icon": c["icon"], "tabs": c["tabs"], "ops": c["ops"], "data": sets}
    return out


# ---- the field catalog, field search and "Add to Hub" mounts ----
def hub_entries(portal):
    """Every catalog entry for one portal (the whole field). Entries without the required fields are ignored, never repaired."""
    if portal not in CATALOG:
        raise PortalError("unknown portal %r" % portal)
    d = _read_json(HUB_CATALOG)
    rows = d.get("entries") if isinstance(d, dict) else None
    return [e for e in (rows or []) if isinstance(e, dict) and e.get("portal") == portal and e.get("id") and e.get("name")]


def hub_meta():
    d = _read_json(HUB_CATALOG)
    return {"present": isinstance(d, dict) and "entries" in d, "editorial": bool(isinstance(d, dict) and d.get("editorial")), "source": (d or {}).get("source") if isinstance(d, dict) else None}


def _mount_path(portal):
    return DATA_DIR / ("hub_%s.json" % portal)


def hub_mounted(portal):
    """The entries the owner has added to this portal, in the order added. Ids that left the catalog drop out."""
    by_id = {e["id"]: e for e in hub_entries(portal)}
    d = _read_json("hub_%s" % portal)
    ids = [i for i in (d.get("mounted") if isinstance(d, dict) else None) or [] if isinstance(i, str)]
    return [by_id[i] for i in ids if i in by_id]


def hub_set(portal, entry_id, on):
    """Add to (on=True) or remove from the portal's hub. Only ids that exist in this portal's catalog can be mounted, so nothing arbitrary is ever injected."""
    by_id = {e["id"]: e for e in hub_entries(portal)}
    if entry_id not in by_id:
        raise PortalError("%r is not in the %s catalog" % (entry_id, portal))
    ids = [e["id"] for e in hub_mounted(portal)]
    if on and entry_id not in ids:
        if len(ids) >= MAX_MOUNTED:
            raise PortalError("this hub already holds %d assets; remove one first" % MAX_MOUNTED)
        ids.append(entry_id)
    elif not on:
        ids = [i for i in ids if i != entry_id]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = _mount_path(portal)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"mounted": ids}, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return hub_mounted(portal)


def run(op, args):
    """Run one op in the axis-logic worker. -> the worker's result dict. Raises PortalError for anything that is not a clean answer."""
    if op not in ALL_OPS:
        raise PortalError("unknown portal operation %r" % op)
    if not available():
        raise PortalError("the axis-logic worker is missing (axis-logic/portal_worker.py)")
    if op == "hub.search":                      # the bridge, not the page, decides which entries are searched: the whole catalog of the one portal named
        a = args if isinstance(args, dict) else {}
        args = {"entries": hub_entries(str(a.get("portal"))), "query": str(a.get("query") or "")[:120], "kind": a.get("kind") or None, "limit": a.get("limit", 24)}
    payload = json.dumps({"op": op, "args": args if isinstance(args, dict) else {}})
    if len(payload) > MAX_BODY:
        raise PortalError("that request is too large")
    if not _SLOTS.acquire(blocking=False):
        raise PortalBusy("three calculations are already running; try again in a moment")
    t0 = time.time()
    try:
        # -I: the worker adds its own folders to the path; nothing from the environment or the current directory can shadow its imports
        p = subprocess.run([sys.executable, "-I", str(WORKER)], input=payload, capture_output=True, text=True, timeout=TIMEOUT_S, cwd=str(WORKER.parent))
    except subprocess.TimeoutExpired:
        raise PortalError("the calculation took longer than %d seconds and was stopped" % TIMEOUT_S)
    finally:
        _SLOTS.release()
    try:
        out = json.loads(p.stdout)
    except ValueError:
        raise PortalError("the axis-logic worker did not return an answer" + ((": " + p.stderr.strip().splitlines()[-1][:200]) if p.stderr.strip() else ""))
    if out.get("status") != "success":
        raise PortalError(str(out.get("message") or "the calculation failed"))
    out["ms"] = int((time.time() - t0) * 1000)
    out["op"] = op
    return out
