"""
mesh_roster.py - runs on the BRIDGE side (imported by your axis_bridge.py).

The bridge is the only thing that looks inside silo_vault. It writes a roster
(engine name -> entry file) that the NEXXUS server reads. The server never scans
or opens the silo folders itself.
"""
import json
import os
from pathlib import Path

ENGINES = [
    "axis-cloud", "axis-core", "axis-curator", "axis-diagnostic", "axis-drive",
    "axis-integrity", "axis-link", "axis-llm", "axis-logic", "axis-omni",
    "axis-phonetic", "axis-port", "axis-SandM", "axis-search_engine",
    "axis-sweep", "axis-triage", "axis-validator", "axis-vantage_point",
    "axis-video_creator", "axis-vision", "render",
]


def roster_path():
    return Path(os.environ.get("NEXXUS_ROSTER") or (Path.cwd() / "mesh_roster.json"))


def _has_marker(p):
    try:
        return "MESH_PROTOCOL" in p.read_text(errors="ignore")
    except OSError:
        return False


def pick_entry(folder):
    """Which file in an engine folder is the engine's entry point? Returns (path, why).
    1. a file where the mesh snippet was pasted (contains MESH_PROTOCOL) - the engine opted in there, so
       that is the file the mesh must run, whatever it is called;
    2. otherwise a *_core.py;  3. otherwise the first .py (a GUESS - flagged by the checker)."""
    folder = Path(folder)
    pys = sorted(p for p in folder.glob("*.py") if p.name != "__init__.py")
    marked = [p for p in pys if _has_marker(p)]
    if marked:
        return marked[0], "mesh snippet found here"
    cores = [p for p in pys if p.name.endswith("_core.py")]
    if cores:
        return cores[0], "*_core.py (no mesh snippet yet)"
    if pys:
        return pys[0], "first .py - a guess (no mesh snippet yet)"
    return None, None


def describe_roster(silo_path):
    """Per engine: the entry file chosen, why, every .py in the folder, and which ones carry the snippet."""
    out = {}
    root = Path(silo_path)
    for name in ENGINES:
        for dn in dict.fromkeys([name, name.lower()]):
            d = root / dn
            if d.is_dir():
                entry, why = pick_entry(d)
                pys = sorted(p.name for p in d.glob("*.py") if p.name != "__init__.py")
                out[name] = {"entry": str(entry) if entry else None, "why": why, "py_files": pys,
                             "marked": [p for p in pys if _has_marker(d / p)]}
                break
    return out


def build_roster(silo_path):
    """Map each known engine to its entry file (see pick_entry)."""
    return {n: d["entry"] for n, d in describe_roster(silo_path).items() if d["entry"]}


def publish_roster(silo_path):
    roster = build_roster(silo_path)
    p = roster_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(roster, indent=2))
    os.replace(tmp, p)
    return roster