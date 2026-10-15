"""integrity_store.py - where axis-integrity's layers (security, bridge, auditor interface) keep what they hold and record. One module, shared by all of them
(each finds it by walking up to the engine root; its name is unique so it can never be confused with the layers' own 'lib' folders).

Everything lives under data/ (override with AXIS_INTEGRITY_DATA; the tests do):
    quarantine/   isolated packets (the Mirror / "Fuchsia" box)         evidence/      forensic dumps         silo_inbox/<silo>/   what the bridge delivered to a silo
    bridge_buffers/<id>/   the bridge's working buffers (wiped after use)  settings.json   the auditor's operating mode     sessions.json   live sessions
Silos themselves are looked up under AXIS_INTEGRITY_SILO_ROOT (default: the folder that holds this engine)."""
import datetime
import hashlib
import json
import os
import re
import tempfile

ENGINE = os.path.dirname(os.path.abspath(__file__))


def data_dir():
    return os.environ.get("AXIS_INTEGRITY_DATA") or os.path.join(ENGINE, "data")


def silo_root():
    return os.environ.get("AXIS_INTEGRITY_SILO_ROOT") or os.path.dirname(ENGINE)


def path(*parts):
    p = os.path.join(data_dir(), *parts)
    os.makedirs(os.path.dirname(p) if os.path.splitext(parts[-1])[1] else p, exist_ok=True)
    return p


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def safe_name(name):
    """A silo or buffer name that can be used as a folder name: letters, digits, '-', '_' and '.', no path tricks. Raises ValueError otherwise."""
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", str(name)) or ".." in str(name):
        raise ValueError("%r is not a valid name (letters, digits, '-', '_', '.'; at most 64 characters)" % (name,))
    return str(name)


def read_json(rel, default=None):
    try:
        with open(path(*rel.split("/")), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(rel, obj):
    p = path(*rel.split("/"))
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, sort_keys=True, default=str)
    os.replace(tmp, p)
    return p


def append_jsonl(rel, rec):
    with open(path(*rel.split("/")), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
    return rec


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_obj(o):
    return sha256_bytes(json.dumps(o, sort_keys=True, default=str).encode())


def as_bytes(packet):
    """Any packet (bytes, str, dict/list, other) as bytes, the same way every time."""
    if isinstance(packet, (bytes, bytearray)):
        return bytes(packet)
    if isinstance(packet, str):
        return packet.encode("utf-8", "replace")
    return json.dumps(packet, sort_keys=True, default=str).encode("utf-8")
