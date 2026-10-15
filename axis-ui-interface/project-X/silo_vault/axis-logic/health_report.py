"""health_report.py - axis-logic, checked for real. Each folder (the silos ecom/sports/stocks/logs, operations, interface, lib, config,
src/silo_manager, gaming_video) is probed in its own process with that folder first on the path, loading every module by file path under a
unique name (the silos each have a signal.py, which must never be mixed up with Python's own `signal`). Exit code 0 only when all import.
Run: python health_report.py"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
FOLDERS = ["lib", "config", "ecom", "sports", "stocks", "logs", "operations", "interface", "src/silo_manager", "src/silo_manager/governor", "gaming_video"]
PROBE = r'''
import importlib.util, json, os, sys
folder, root = sys.argv[1], sys.argv[2]
sys.path.insert(0, folder)
for p in (os.path.join(root, "lib"), root, os.path.join(root, "src", "silo_manager")):
    if p not in sys.path:
        sys.path.append(p)
out = {}
for f in sorted(os.listdir(folder)):
    if not f.endswith(".py") or f == "__init__.py":
        continue
    path = os.path.join(folder, f)
    code = [l for l in open(path, encoding="utf-8", errors="replace").read().splitlines() if l.strip() and not l.strip().startswith("#")]
    try:
        spec = importlib.util.spec_from_file_location("probe_" + f[:-3], path)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        out[f] = ["PARAMS" if len(code) <= 3 else "OK", ""]
    except BaseException as e:
        out[f] = ["IMPORT_ERROR", "%s: %s" % (type(e).__name__, str(e)[:120])]
print("@@" + json.dumps(out))
'''


def check(folder):
    path = os.path.join(ROOT, *folder.split("/"))
    r = subprocess.run([sys.executable, "-c", PROBE, path, ROOT], cwd=path, capture_output=True, text=True, timeout=180,
                       env=dict(os.environ, NEXXUS_MESH_URL="http://127.0.0.1:9", PYTHONDONTWRITEBYTECODE="1"))
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@")), None)
    return json.loads(line[2:]) if line else {"<probe>": ["PROBE_FAILED", (r.stderr.strip().splitlines() or ["no output"])[-1][:120]]}


def main():
    bad = 0
    for folder in FOLDERS:
        res = check(folder)
        counts = {}
        for st, _ in res.values():
            counts[st] = counts.get(st, 0) + 1
        broke = {k: v for k, v in res.items() if v[0] in ("IMPORT_ERROR", "PROBE_FAILED")}
        bad += len(broke)
        print("%-26s %s" % (folder, "  ".join("%s %d" % (k, v) for k, v in sorted(counts.items()))))
        for k, (st, why) in sorted(broke.items()):
            print("    %-13s %s  %s" % (st, k, why))
    print("\n%s" % ("ALL MODULES IMPORT" if not bad else "%d problem(s)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
