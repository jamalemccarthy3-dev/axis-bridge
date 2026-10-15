"""operator_scope.py - operator mode (v1) may act ONLY inside folders the user has explicitly granted.

Deny by default: with no grants, every path is refused. A path is allowed only if its real location (symlinks and `..` resolved, case-folded on Windows) sits inside a granted folder.
Granting a folder does not grant its parents or siblings. Drive roots and the user's home folder itself cannot be granted. Every decision, allowed or refused, is appended to
logs/operator_audit.jsonl. Anything that performs an operator action must call `require(path)` first and let the PermissionError stand.
"""
import json
import os
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GRANTS_PATH = os.path.join(HERE, "nexxus_data", "state", "operator_grants.json")
AUDIT_PATH = os.path.join(HERE, "logs", "operator_audit.jsonl")
_LOCK = threading.RLock()


def _real(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(str(path)))))


def _audit(action, path, allowed, reason):
    try:
        os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "action": action, "path": str(path)[:500], "allowed": allowed, "reason": reason}) + "\n")
    except OSError:
        pass


def grants():
    with _LOCK:
        try:
            with open(GRANTS_PATH, encoding="utf-8") as f:
                g = json.load(f)
            return [x for x in g.get("folders", []) if isinstance(x, str)]
        except (OSError, ValueError, AttributeError):
            return []


def _store(folders):
    os.makedirs(os.path.dirname(GRANTS_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(GRANTS_PATH), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"folders": folders}, f)
    os.replace(tmp, GRANTS_PATH)


def grant(folder):
    """Explicitly allow operator mode inside `folder`. -> (ok, reason)."""
    real = _real(folder)
    if not os.path.isdir(real):
        _audit("grant", folder, False, "not an existing folder")
        return False, "not an existing folder"
    if os.path.dirname(real) == real or real == _real("~"):
        _audit("grant", folder, False, "too broad (drive root or home)")
        return False, "too broad: a drive root or your home folder cannot be granted"
    with _LOCK:
        cur = grants()
        if real not in cur:
            _store(cur + [real])
    _audit("grant", real, True, "granted")
    return True, "granted"


def revoke(folder):
    real = _real(folder)
    with _LOCK:
        cur = grants()
        _store([x for x in cur if x != real])
    _audit("revoke", real, True, "revoked")
    return real in cur


def check(path, action="access"):
    """-> (allowed, reason). Never raises."""
    try:
        real = _real(path)
    except (OSError, ValueError):
        _audit(action, path, False, "unresolvable path")
        return False, "unresolvable path"
    for g in grants():
        try:
            if os.path.commonpath([real, g]) == g:
                _audit(action, real, True, "inside granted folder")
                return True, "inside granted folder"
        except ValueError:      # different drives
            continue
    _audit(action, real, False, "outside every granted folder" if grants() else "no folders granted")
    return False, "outside every granted folder" if grants() else "no folders granted"


def require(path, action="access"):
    ok, why = check(path, action)
    if not ok:
        raise PermissionError("operator mode is limited to granted folders: " + why)
    return _real(path)
