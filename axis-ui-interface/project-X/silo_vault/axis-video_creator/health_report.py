"""health_report.py - checks every silo for real: the folder exists, its modules are more than stubs, and every module imports.
Each silo is checked in its own process (silos share folder names like lib/ and config/). Exit code 0 only when nothing is broken.
Run:  python health_report.py"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from config.master_config import GOVERNANCE_OPTIONAL, MASTER_CONFIG, SILO_REGISTRY  # noqa: E402

PROBE = r"""
import importlib, json, os, sys
folder, root = sys.argv[1], sys.argv[2]
sys.path.insert(0, folder); sys.path.append(root)
out = {}
files = [f for f in sorted(os.listdir(folder)) if f.endswith(".py") and f != "__init__.py"]
for sub in ("lib", "config"):
    d = os.path.join(folder, sub)
    if os.path.isdir(d):
        files += [sub + "/" + f for f in sorted(os.listdir(d)) if f.endswith(".py") and f != "__init__.py"]
for f in files:
    code = [l for l in open(os.path.join(folder, f), encoding="utf-8", errors="replace").read().splitlines() if l.strip() and not l.strip().startswith("#")]
    try:
        importlib.import_module(f[:-3].replace("/", "."))
        out[f] = ["STUB" if (len(code) <= 2 or any("# STUB:" in l for l in open(os.path.join(folder, f), encoding="utf-8", errors="replace"))) else "OK", ""]
    except BaseException as e:
        out[f] = ["IMPORT_ERROR", "%s: %s" % (type(e).__name__, str(e)[:110])]
print("@@" + json.dumps(out))
"""


def check(name, rel):
    folder = os.path.join(ROOT, rel)
    if not os.path.isdir(folder):
        return {"<folder>": ["MISSING", rel]}
    r = subprocess.run([sys.executable, "-c", PROBE, folder, ROOT], cwd=folder, capture_output=True, text=True, timeout=120)
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@")), None)
    return json.loads(line[2:]) if line else {"<probe>": ["PROBE_FAILED", (r.stderr.strip().splitlines() or ["no output"])[-1][:110]]}


def main():
    bad = 0
    for name, rel in SILO_REGISTRY.items():
        res = check(name, rel)
        counts = {}
        for st, _ in res.values():
            counts[st] = counts.get(st, 0) + 1
        broke = {k: v for k, v in res.items() if v[0] in ("MISSING", "IMPORT_ERROR", "PROBE_FAILED")}
        bad += len(broke)
        print("%-20s %s" % (name, "  ".join("%s %d" % (k, v) for k, v in sorted(counts.items()))))
        for k, (st, why) in broke.items():
            print("    %-13s %s  %s" % (st, k, why))
    for key, f in MASTER_CONFIG["nexxus_governance"].items():
        ok = os.path.isfile(os.path.join(ROOT, f))
        optional = key in GOVERNANCE_OPTIONAL
        bad += 0 if (ok or optional) else 1
        print("governance %-22s %s" % (key, "PRESENT" if ok else ("not installed (optional)" if optional else "MISSING")))
    print("\n%s" % ("ALL SILOS IMPORT" if not bad else "%d problem(s)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
