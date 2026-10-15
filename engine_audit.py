"""engine_audit.py - one honest table for every engine in the silo: how much real code, how much is stub, what fails to import,
and whether it still claims "VERIFIED" without checking. Read-only. Run:  python engine_audit.py [engine-name ...]

Each engine is probed in its own process with its own folder first on sys.path. Heartbeats are pointed at a dead address, so the probe can
never make a broken engine look 'live' on the NEXXUS dashboard. Modules named main/master_run/mesh/live_status/bridge_* and anything with
a `while True` at module level are not imported (they run things); they are only counted.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SILO = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault")
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "logs", "dist", "build", "builds", "venv", "env", "bridge_env", "instantmesh_env", "tests"}
NO_IMPORT = re.compile(r"^(main|master_run|mesh|live_status|bridge_(?:diagnostic|orders)|deployment_tool|__init__|setup|conftest)$")
CLAIM = re.compile(r"READY_AND_OPERATIONAL|VERIFIED_LIVE|FULL_SUITE_VERIFIED|100% Verification")

PROBE = r'''
import importlib, json, os, re, sys
folder = sys.argv[1]; files = json.loads(sys.argv[2])
sys.path.insert(0, folder)
out = {}
for rel in files:
    mod = rel[:-3].replace(os.sep, ".").replace("/", ".")
    try:
        importlib.import_module(mod); out[rel] = ""
    except BaseException as e:
        out[rel] = "%s: %s" % (type(e).__name__, str(e)[:100])
print("@@" + json.dumps(out))
'''


def engines():
    return sorted(d for d in os.listdir(SILO) if os.path.isdir(os.path.join(SILO, d)) and not d.startswith(("_", ".")) and d not in ("render", "nexxus")
                  and os.path.isfile(os.path.join(SILO, d, "bridge_diagnostic.py")))


def py_files(folder):
    for dp, dn, fn in os.walk(folder):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if f.endswith(".py"):
                yield os.path.relpath(os.path.join(dp, f), folder)


def code_lines(path):
    try:
        return sum(1 for l in open(path, encoding="utf-8", errors="replace") if l.strip() and not l.strip().startswith("#"))
    except OSError:
        return 0


def audit(name):
    folder = os.path.join(SILO, name)
    files = sorted(py_files(folder))
    lines = {f: code_lines(os.path.join(folder, f)) for f in files}
    stubs = [f for f, n in lines.items() if n <= 3 and not f.endswith("__init__.py")]
    claims = [f for f in files if CLAIM.search(open(os.path.join(folder, f), encoding="utf-8", errors="replace").read())]
    importable = []
    for f in files:
        base = os.path.basename(f)[:-3]
        text = open(os.path.join(folder, f), encoding="utf-8", errors="replace").read()
        if NO_IMPORT.match(base) or re.search(r"^while True", text, re.M) or lines[f] == 0:
            continue
        importable.append(f)
    errs = {}
    if importable:
        env = dict(os.environ, NEXXUS_MESH_URL="http://127.0.0.1:9", PYTHONDONTWRITEBYTECODE="1")
        try:
            r = subprocess.run([sys.executable, "-c", PROBE, folder, json.dumps(importable)], cwd=folder, capture_output=True, text=True, timeout=180, env=env)
            line = next((l for l in r.stdout.splitlines() if l.startswith("@@")), None)
            errs = {k: v for k, v in json.loads(line[2:]).items() if v} if line else {"<probe>": (r.stderr.strip().splitlines() or ["no output"])[-1][:100]}
        except subprocess.TimeoutExpired:
            errs = {"<probe>": "timed out after 180 s (something runs at import)"}
    return {"engine": name, "py_files": len(files), "code_lines": sum(lines.values()), "stubs": len(stubs), "importable": len(importable),
            "import_errors": errs, "false_claims": claims, "own_repo": os.path.isdir(os.path.join(folder, ".git")),
            "has_master_test": any(os.path.basename(f).startswith("master_test") for f in files)}


def main(argv):
    names = argv or engines()
    results = [audit(n) for n in names]
    print("%-24s %5s %6s %6s %7s %7s %6s" % ("engine", "files", "lines", "stubs", "import", "errors", "claims"))
    for r in results:
        print("%-24s %5d %6d %6d %7d %7d %6d  %s" % (r["engine"], r["py_files"], r["code_lines"], r["stubs"], r["importable"], len(r["import_errors"]), len(r["false_claims"]), "own repo" if r["own_repo"] else ""))
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    with open(os.path.join(ROOT, "logs", "engine_audit.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    print("\ndetails: logs/engine_audit.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
