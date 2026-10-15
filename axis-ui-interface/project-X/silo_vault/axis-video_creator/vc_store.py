"""vc_store.py - the one place axis-video_creator keeps what it makes and knows. Every silo tool imports it (they find it by walking up to the engine root).

Everything lives under the workspace folder (default: <engine>/workspace, override with the VC_WORKSPACE environment variable; the tests do):
    sessions/<id>.json        interview sessions        projects/<id>/            one folder per video project (state, frames, video, reports)
    assets/                   generated images          data/                     registries and manifests        qc/   inspector reports
Nothing here uses a network."""
import datetime
import hashlib
import importlib.util
import json
import os
import re
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
RESOLUTIONS = {"4k": (3840, 2160), "2k": (2560, 1440), "1080p": (1920, 1080), "720p": (1280, 720), "480p": (854, 480), "360p": (640, 360), "240p": (426, 240)}


def workspace():
    return os.environ.get("VC_WORKSPACE") or os.path.join(ROOT, "workspace")


def resolve(path):
    """A configured path -> a real path inside the workspace. Relative paths ('./data/x.json', 'data/x.json') and unix-style absolute ones ('/exports/final/')
    are both placed under the workspace, so a config can never point a tool outside it."""
    p = str(path).replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", p) and os.path.isabs(path):
        return os.path.abspath(path)                      # a real Windows path somebody chose on purpose (tests use temp folders)
    parts = [x for x in p.split("/") if x not in ("", ".", "..")]
    return os.path.join(workspace(), *parts)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _parent(p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def read_json(path, default=None):
    try:
        with open(resolve(path), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    p = _parent(resolve(path))
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, sort_keys=True, default=str)
    os.replace(tmp, p)
    return p


def append_jsonl(path, rec):
    with open(_parent(resolve(path)), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
    return rec


def read_jsonl(path):
    out = []
    try:
        with open(resolve(path), encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        out.append({"_unreadable": line[:80]})
    except OSError:
        pass
    return out


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_obj(obj):
    """Hash of a JSON-able object that does not depend on key order."""
    return sha256_bytes(json.dumps(obj, sort_keys=True, default=str).encode())


def parse_resolution(res):
    """'4k' / '1080p' / '1280x720' / (w, h) -> (w, h). Raises ValueError for anything else."""
    if isinstance(res, (tuple, list)) and len(res) == 2:
        return int(res[0]), int(res[1])
    r = str(res).lower().strip()
    if r in RESOLUTIONS:
        return RESOLUTIONS[r]
    m = re.match(r"^(\d{2,5})x(\d{2,5})$", r)
    if not m:
        raise ValueError("unknown resolution %r (use one of %s or WIDTHxHEIGHT)" % (res, sorted(RESOLUTIONS)))
    return int(m.group(1)), int(m.group(2))


def load_module(relpath, name=None):
    """Loads a module of this engine by file path (the silos reuse the folder names lib/ and config/, so import names would collide)."""
    spec = importlib.util.spec_from_file_location(name or "vc_" + re.sub(r"\W", "_", relpath[:-3]), os.path.join(ROOT, *relpath.split("/")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_func(relpath, func):
    return getattr(load_module(relpath), func)


def project_dir(project_id):
    if not re.match(r"^[A-Za-z0-9_.-]{1,64}$", str(project_id)):
        raise ValueError("a project id is 1-64 letters, digits, '_', '-' or '.'")
    d = os.path.join(workspace(), "projects", project_id)
    os.makedirs(d, exist_ok=True)
    return d


def heartbeat(silo, note=""):
    return write_json("data/heartbeats/%s.json" % silo, {"silo": silo, "ts": datetime.datetime.now().timestamp(), "at": now(), "note": note})


def log(actor, action, status="ok"):
    """One line in the engine's compliance log, hash-chained to the line before it (editing an old line is then detectable)."""
    rel = "logs/governance_audit.log"
    prev = "0" * 64
    for r in read_jsonl(rel):
        prev = r.get("hash", prev)
    rec = {"ts": now(), "actor": str(actor), "action": str(action), "status": str(status), "prev": prev}
    rec["hash"] = sha256_obj({k: v for k, v in rec.items() if k != "hash"})
    return append_jsonl(rel, rec)
