"""sandm_store.py - where axis-SandM keeps what it knows. One small module every tool shares (it sits at the engine root, so every silo can import it).

Files live under data/ (override the folder with the SANDM_DATA environment variable; the tests do). Nothing here talks to a network.
  data/state/*.json       current state of one thing (the registry, the halt flag, a heartbeat ...)
  data/*.jsonl            append-only records (the audit trail, dispatches, reports ...)
  data/inbox/<name>/      where outside information arrives: drop .json or .jsonl files there (metrics, trend signals, competitor notes, click logs ...).
A tool that has no input says so ("no_data") - it never invents numbers.
"""
import datetime
import glob
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))


def data_dir():
    return os.environ.get("SANDM_DATA") or os.path.join(ROOT, "data")


def resolve(path):
    """A configured path -> a real path on this machine. Absolute paths stay; 'data/...' and other relative paths live under the data folder."""
    if os.path.isabs(path) or path.startswith(("/", "\\")):
        return os.path.join(data_dir(), "external", os.path.basename(path.rstrip("/\\")))      # a unix-style absolute path from a config cannot exist here: keep it inside data/
    parts = path.replace("\\", "/").split("/")
    if parts[0] == "data":
        parts = parts[1:]
    return os.path.join(data_dir(), *parts)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _make_parent(p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def read_json(rel, default=None):
    try:
        with open(resolve(rel), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(rel, obj):
    p = _make_parent(resolve(rel))
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, p)
    return p


def append_jsonl(rel, rec):
    with open(_make_parent(resolve(rel)), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def read_jsonl(rel):
    out = []
    try:
        with open(resolve(rel), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        out.append({"_unreadable": line[:80]})
    except OSError:
        pass
    return out


def inbox(name):
    """Every record dropped into data/inbox/<name>/ (.json holding an object or a list, .jsonl one object per line), oldest file first."""
    out = []
    for p in sorted(glob.glob(os.path.join(resolve("inbox/" + name), "*"))):
        try:
            with open(p, encoding="utf-8") as f:
                if p.endswith(".jsonl"):
                    out += [json.loads(l) for l in f if l.strip()]
                elif p.endswith(".json"):
                    d = json.load(f)
                    out += d if isinstance(d, list) else [d]
        except (OSError, ValueError):
            out.append({"_unreadable": os.path.basename(p)})
    return [r for r in out if isinstance(r, dict)]


def engine_path(*parts):
    return os.path.join(ROOT, *parts)


def audit(actor, action, status="ok"):
    """Write to the governor's audit trail from any silo."""
    root = os.path.join(ROOT, "src", "governor", "lib")
    if root not in sys.path:
        sys.path.append(root)
    import importlib.util
    spec = importlib.util.spec_from_file_location("sandm_audit_trail", os.path.join(root, "audit_trail_logger_tool.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.AuditTrailLoggerEngine(None).log_event(actor, action, status)


def halted():
    """-> the halt record if the emergency kill switch has fired and nobody has cleared it, else None. Agents must refuse to start while this is set."""
    return read_json("state/halted.json")


def master_config():
    """The engine's MasterConfig. Loaded by file path, because inside a silo the name 'config' means that silo's own config folder."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sandm_master_config", os.path.join(ROOT, "config", "master_config.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.MasterConfig()


def load_engine(relpath, class_name, config=None):
    """Load another silo's engine class by file path (silos keep clashing 'lib'/'config' folder names, so never by import name)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sandm_" + os.path.basename(relpath)[:-3], os.path.join(ROOT, *relpath.split("/")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, class_name)(config)


def beat(silo):
    """A silo's heartbeat: stamped when its agent starts or does work, read by the governor's heartbeat monitor."""
    import time
    return write_json("state/heartbeats/%s.json" % silo, {"silo": silo, "ts": time.time(), "at": now()})


def load_class(relpath, class_name):
    """The class itself, loaded by file path (for config classes, which take no arguments)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sandm_c_" + os.path.basename(relpath)[:-3], os.path.join(ROOT, *relpath.split("/")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, class_name)
