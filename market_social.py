"""market_social.py - star ratings and threaded comments for Marketplace products.

Ratings are social proof, so they must be real:
  * A review needs a VERIFIED interaction. For a Free and Open product that is a recorded download of the package. For a paid product it is a purchase that the administrator has attested (NEXXUS cannot see
    payments itself). No interaction, no review.
  * One review per person per product (a second one replaces the first), 1 to 5 stars, with optional text.
  * You cannot review your own product.
  * The average and the count come only from stored, verified reviews. With none, there is no rating: the page says so, and the search metadata carries no aggregateRating.

Comments are open to anyone who can see the product, threaded (replies up to 3 levels), limited in length and rate, and removable by their author, the product's creator or the administrator. A removed comment
leaves a "[removed]" marker so a thread still reads. Everything here is public product content: it never touches private messages (see privacy.py).
"""
import json
import os
import re
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "nexxus_data", "marketplace")
REVIEWS_PATH = os.path.join(DATA_DIR, "reviews.json")
COMMENTS_PATH = os.path.join(DATA_DIR, "comments.json")
INTERACTIONS_PATH = os.path.join(DATA_DIR, "interactions.jsonl")
_LOCK = threading.RLock()
MAX_REVIEW = 500
MAX_COMMENT = 500
MAX_DEPTH = 3
COMMENTS_PER_HOUR = 20
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_recent = {}


class SocialError(ValueError):
    pass


def _clean(s, n):
    return _CTRL.sub("", str(s or "")).strip()[:n]


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, type(default)) else default
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# ---------------------------------------------------------------- verified interactions
def record_interaction(pid, who, kind):
    """kind is 'download' (recorded by the download route) or 'purchase' (attested by the administrator)."""
    if kind not in ("download", "purchase") or not _clean(who, 40):
        raise SocialError("Unknown interaction.")
    with _LOCK:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(INTERACTIONS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time()), "pid": str(pid), "who": _clean(who, 40), "kind": kind}) + "\n")


def _interactions(pid, who):
    out = set()
    try:
        with open(INTERACTIONS_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("pid") == str(pid) and r.get("who") == who:
                    out.add(r.get("kind"))
    except OSError:
        pass
    return out


def can_review(pid, who, tier, owner):
    """-> (ok, reason). The reason is shown to the person, so it says exactly what is missing."""
    who = _clean(who, 40)
    if not who:
        return False, "Add a name to your profile first so your review has an author."
    if who == _clean(owner, 40):
        return False, "You cannot review your own product."
    have = _interactions(pid, who)
    if tier == "free":
        return ("download" in have, "") if "download" in have else (False, "Download the package first: only people who have actually downloaded it can review it.")
    return ("purchase" in have, "") if "purchase" in have else (False, "Paid products can be reviewed only after the administrator has verified your purchase.")


# ---------------------------------------------------------------- reviews
def add_review(pid, who, stars, text, tier, owner):
    ok, why = can_review(pid, who, tier, owner)
    if not ok:
        raise SocialError(why)
    try:
        stars = int(stars)
    except (TypeError, ValueError):
        raise SocialError("Choose 1 to 5 stars.")
    if not 1 <= stars <= 5:
        raise SocialError("Choose 1 to 5 stars.")
    who = _clean(who, 40)
    with _LOCK:
        data = _load(REVIEWS_PATH, {})
        rows = [r for r in data.get(str(pid), []) if r["who"] != who]                      # a second review replaces the first
        rows.append({"id": uuid.uuid4().hex[:10], "who": who, "stars": stars, "text": _clean(text, MAX_REVIEW), "t": int(time.time()), "verified": "download" if tier == "free" else "purchase"})
        data[str(pid)] = rows
        _save(REVIEWS_PATH, data)
    return summary(pid)


def summary(pid):
    rows = _load(REVIEWS_PATH, {}).get(str(pid), [])
    n = len(rows)
    dist = {str(i): sum(1 for r in rows if r["stars"] == i) for i in range(5, 0, -1)}
    return {"count": n, "avg": round(sum(r["stars"] for r in rows) / n, 1) if n else 0, "dist": dist}


def reviews(pid, limit=50):
    rows = _load(REVIEWS_PATH, {}).get(str(pid), [])
    return [{"id": r["id"], "who": r["who"], "stars": r["stars"], "text": r["text"], "t": r["t"], "verified": r["verified"]} for r in reversed(rows)][:limit]


# ---------------------------------------------------------------- comments
def add_comment(pid, who, text, parent=None):
    who, text = _clean(who, 40), _clean(text, MAX_COMMENT)
    if not who or not text:
        raise SocialError("Write a comment, signed in with a profile name.")
    now = time.time()
    with _LOCK:
        key = (who, str(pid))
        _recent[key] = [t for t in _recent.get(key, []) if now - t < 3600]
        if len(_recent[key]) >= COMMENTS_PER_HOUR:
            raise SocialError("Slow down: too many comments this hour.")
        data = _load(COMMENTS_PATH, {})
        rows = data.get(str(pid), [])
        depth = 1
        if parent:
            p = next((r for r in rows if r["id"] == str(parent)), None)
            if not p:
                raise SocialError("The comment you are replying to is gone.")
            depth = p["depth"] + 1
            if depth > MAX_DEPTH:
                raise SocialError("Replies go three levels deep; reply to the thread's last comment instead.")
        c = {"id": uuid.uuid4().hex[:10], "who": who, "text": text, "t": int(now), "parent": str(parent) if parent else None, "depth": depth, "removed": False}
        rows.append(c)
        data[str(pid)] = rows[-500:]
        _save(COMMENTS_PATH, data)
        _recent[key].append(now)
    return c


def remove_comment(cid, actor, is_admin=False, is_owner=False):
    with _LOCK:
        data = _load(COMMENTS_PATH, {})
        for pid, rows in data.items():
            for r in rows:
                if r["id"] == str(cid):
                    if not (r["who"] == _clean(actor, 40) or is_admin or is_owner):
                        raise SocialError("Only the author, the product's creator or the administrator can remove a comment.")
                    r["removed"] = True
                    r["text"] = ""
                    _save(COMMENTS_PATH, data)
                    return pid
    raise SocialError("No such comment.")


def comment_tree(pid):
    rows = _load(COMMENTS_PATH, {}).get(str(pid), [])
    by_parent = {}
    for r in rows:
        by_parent.setdefault(r["parent"], []).append(r)

    def build(parent):
        out = []
        for r in by_parent.get(parent, []):
            out.append({"id": r["id"], "who": r["who"] if not r["removed"] else "", "text": r["text"] if not r["removed"] else "[removed]", "t": r["t"], "removed": r["removed"], "replies": build(r["id"])})
        return out
    return build(None)


def count_comments(pid):
    return sum(1 for r in _load(COMMENTS_PATH, {}).get(str(pid), []) if not r["removed"])
