"""health_report.py - axis-validator, checked for real. Every module in src/ (and its lib/ and config/) is imported in one process with src/ first on the
path, which is how the modules themselves expect to run (they import `config.*` and `lib.*` relative to src/). Exit code 0 only when all import.
Run: python health_report.py"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PROBE = r'''
import importlib, json, os, sys
src = sys.argv[1]
sys.path.insert(0, src)
out = {}
for sub in ("", "lib", "config"):
    d = os.path.join(src, sub)
    for f in sorted(os.listdir(d)):
        if not f.endswith(".py") or f == "__init__.py":
            continue
        rel = (sub + "/" if sub else "") + f
        code = [l for l in open(os.path.join(d, f), encoding="utf-8", errors="replace").read().splitlines() if l.strip() and not l.strip().startswith("#")]
        try:
            importlib.import_module((sub + "." if sub else "") + f[:-3])
            out[rel] = ["STUB" if len(code) <= 3 else "OK", ""]
        except BaseException as e:
            out[rel] = ["IMPORT_ERROR", "%s: %s" % (type(e).__name__, str(e)[:120])]
print("@@" + json.dumps(out))
'''


def check():
    r = subprocess.run([sys.executable, "-c", PROBE, os.path.join(ROOT, "src")], cwd=ROOT, capture_output=True, text=True, timeout=180,
                       env=dict(os.environ, NEXXUS_MESH_URL="http://127.0.0.1:9", PYTHONDONTWRITEBYTECODE="1"))
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@")), None)
    return json.loads(line[2:]) if line else {"<probe>": ["PROBE_FAILED", (r.stderr.strip().splitlines() or ["no output"])[-1][:120]]}


def main():
    res = check()
    counts = {}
    for st, _ in res.values():
        counts[st] = counts.get(st, 0) + 1
    print("src  " + "  ".join("%s %d" % (k, v) for k, v in sorted(counts.items())))
    broke = {k: v for k, v in res.items() if v[0] in ("IMPORT_ERROR", "PROBE_FAILED")}
    for k, (st, why) in sorted(broke.items()):
        print("    %-13s %s  %s" % (st, k, why))
    print("\n%s" % ("ALL MODULES IMPORT" if not broke else "%d problem(s)" % len(broke)))
    return 1 if broke else 0


if __name__ == "__main__":
    sys.exit(main())
