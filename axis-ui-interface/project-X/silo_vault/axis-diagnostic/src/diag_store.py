"""diag_store.py - where axis-diagnostic keeps what it learns and records (the engine's data/ folder; override with AXIS_DIAGNOSTIC_DATA, the tests do).
Configured paths such as "/sys/registry/root" or "internal_bus://telemetry" are mapped to files inside that folder, so a config can never point a utility at the real system."""
import datetime
import hashlib
import json
import os
import re
import tempfile

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    return os.environ.get("AXIS_DIAGNOSTIC_DATA") or os.path.join(ENGINE, "data")


def resolve(name):
    """'/sys/registry/root' -> <data>/sys/registry/root ; 'internal_bus://telemetry' -> <data>/internal_bus/telemetry ; 'sys_log_alert' -> <data>/sys_log_alert."""
    parts = [p for p in re.split(r"[\\/:]+", str(name)) if p and p not in (".", "..")]
    return os.path.join(data_dir(), *parts)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def read_json(name, default=None):
    try:
        with open(resolve(name) + ".json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(name, obj):
    path = resolve(name) + ".json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return path


def append_jsonl(name, rec):
    path = resolve(name) + ".jsonl"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
    return rec


def read_jsonl(name):
    out = []
    try:
        with open(resolve(name) + ".jsonl", encoding="utf-8") as f:
            out = [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        pass
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
