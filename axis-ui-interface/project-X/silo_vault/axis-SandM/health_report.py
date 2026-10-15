"""health_report.py - checks every utility of every silo for real: does the file exist, is it more than a stub, and does it import?
Each silo is checked in its own process (the silos share folder names like lib/ and config/), so one broken silo cannot hide another.
Run:  python health_report.py        Exit code 0 only when every utility imports.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from config.master_config import MasterConfig  # noqa: E402

PROBE = r'''
import importlib, json, os, sys
folder, names = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, folder)
out = {}
for n in names:
    p = os.path.join(folder, n)
    if not os.path.isfile(p):
        out[n] = ["MISSING", ""]; continue
    code = [l for l in open(p, encoding="utf-8", errors="replace").read().splitlines() if l.strip() and not l.strip().startswith("#")]
    try:
        importlib.import_module(n[:-3]); out[n] = ["STUB" if len(code) <= 3 else "OK", ""]
    except BaseException as e:
        out[n] = ["IMPORT_ERROR", "%s: %s" % (type(e).__name__, str(e)[:110])]
print("@@" + json.dumps(out))
'''


def check_silo(cfg, name):
    folder = cfg.silo_folder(name)
    names = [u for u in cfg.silos[name]["utilities"] if u != "tool_request.py"]    # the agent itself is started and checked by main.py
    r = subprocess.run([sys.executable, "-c", PROBE, folder, json.dumps(names)], cwd=folder, capture_output=True, text=True, timeout=120)
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@")), None)
    if not line:
        return {n: ["PROBE_FAILED", (r.stderr.strip().splitlines() or ["no output"])[-1][:110]] for n in names}
    return json.loads(line[2:])


def main():
    cfg = MasterConfig()
    bad = 0
    for name in cfg.silos:
        res = check_silo(cfg, name)
        counts = {}
        for st, _ in res.values():
            counts[st] = counts.get(st, 0) + 1
        broke = {k: v for k, v in res.items() if v[0] in ("MISSING", "IMPORT_ERROR", "PROBE_FAILED")}
        bad += len(broke)
        print("%-24s %s" % (name, "  ".join("%s %d" % (k, v) for k, v in sorted(counts.items()))))
        for k, (st, why) in broke.items():
            print("    %-14s %s  %s" % (st, k, why))
    for key, f in cfg.governance.items():
        ok = os.path.isfile(os.path.join(ROOT, f))
        optional = key in cfg.governance_optional
        bad += 0 if (ok or optional) else 1
        print("governance %-22s %s" % (key, "PRESENT" if ok else ("not installed (optional: only peer-reviewer engines carry it)" if optional else "MISSING (%s)" % f)))
    print("\n%s" % ("ALL UTILITIES IMPORT" if not bad else "%d problem(s)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
