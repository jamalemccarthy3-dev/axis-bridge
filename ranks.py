"""ranks.py - the transparent ranking engine.

Your rank comes from ONE place: a ledger of points that you can read in full. Each entry says what earned it, how many points, and what it refers to. There are no hidden metrics: nothing else is
measured, nothing else counts, and the rules below are the whole formula (the dashboard shows this same table next to your ledger).

Only PUBLIC contributions earn points (see privacy.py): private messages, group chats and live rooms never count and are never looked at. Rules marked available=False describe contributions that need
parts of the platform that do not exist yet (pods, peer support); they earn nothing today and are listed so nothing is hidden about what will.

Anti-gaming that is also visible: a daily cap per rule, one award per item, and no points for interacting with yourself.
"""
import json
import os
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER_PATH = os.path.join(HERE, "nexxus_data", "platform", "ranks.jsonl")
_LOCK = threading.RLock()

RULES = {
    "public_post": {"points": 2, "daily_cap": 5, "available": True, "text": "You shared a post publicly on the public wall (2 points each, up to 5 posts a day)."},
    "peer_comment_received": {"points": 1, "daily_cap": 10, "available": True, "text": "Another person commented on your public post (1 point each, up to 10 a day). Comments you write on your own posts earn nothing."},
    "pod_task_completed": {"points": 5, "daily_cap": 5, "available": False, "text": "You completed a task in a pod (needs pods, which are not built yet)."},
    "peer_support_given": {"points": 3, "daily_cap": 5, "available": False, "text": "A helpful comment of yours on someone else's public post was marked helpful by them (needs other people on the platform)."},
}
TIERS = (("Newcomer", 0), ("Apprentice", 10), ("Builder", 30), ("Craftsman", 80), ("Master", 200))


def _read():
    out = []
    try:
        with open(LEDGER_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _day(t):
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def award(rule, ref, note="", now=None):
    """Add points for a public contribution. -> the ledger entry, or None (rule unavailable, already awarded for this item, or the daily cap is reached)."""
    r = RULES.get(rule)
    if not r or not r["available"] or not ref:
        return None
    now = time.time() if now is None else now
    with _LOCK:
        ledger = _read()
        if any(e["rule"] == rule and e["ref"] == str(ref) for e in ledger):
            return None
        if sum(1 for e in ledger if e["rule"] == rule and _day(e["t"]) == _day(now)) >= r["daily_cap"]:
            return None
        entry = {"t": int(now), "rule": rule, "points": r["points"], "ref": str(ref)[:40], "note": str(note)[:100]}
        os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
        with open(LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry


def revoke(rule, ref):
    """Take back the points for an item that is no longer public or was deleted, so the ledger always matches what is really public."""
    with _LOCK:
        ledger = _read()
        kept = [e for e in ledger if not (e["rule"] == rule and e["ref"] == str(ref))]
        if len(kept) == len(ledger):
            return False
        os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
        tmp = LEDGER_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for e in kept:
                f.write(json.dumps(e) + "\n")
        os.replace(tmp, LEDGER_PATH)
        return True


def tier_for(points):
    name = TIERS[0][0]
    for t, need in TIERS:
        if points >= need:
            name = t
    return name


def status():
    ledger = _read()
    pts = sum(e["points"] for e in ledger)
    nxt = next(((t, need) for t, need in TIERS if need > pts), None)
    by_rule = {k: {"points": sum(e["points"] for e in ledger if e["rule"] == k), "count": sum(1 for e in ledger if e["rule"] == k)} for k in RULES}
    return {"points": pts, "tier": tier_for(pts), "next_tier": nxt[0] if nxt else None, "to_next": (nxt[1] - pts) if nxt else 0,
            "tiers": [{"name": t, "from": n} for t, n in TIERS], "rules": RULES, "by_rule": by_rule, "ledger": list(reversed(ledger))[:100],
            "note": "This ledger is the whole formula. Nothing else is measured, and private messages, group chats and live rooms never count."}
