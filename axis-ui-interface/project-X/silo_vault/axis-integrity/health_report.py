"""health_report.py - axis-integrity, checked for real. Its three layers (auditor_interface, src/bridge, src/security) each import their
own lib/ and config/ modules by flat name, so each layer is probed in its own process with its own folders on the path (the engine root
last, for the shared lib/). Exit code 0 only when every module imports. Run: python health_report.py"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
LAYERS = ["auditor_interface", "src/bridge", "src/security", "lib"]
SKIP = {"__init__.py"}

PROBE = r'''
import importlib, json, os, sys
layer, root = sys.argv[1], sys.argv[2]
files = json.loads(sys.argv[3])
sys.path.insert(0, layer)
sys.path.insert(0, root)                     # the engine's shared lib/ wins the name `lib` (the request files use it)
for p in (os.path.join(layer, "lib"), os.path.join(layer, "config")):
    sys.path.insert(0, p)                    # the layer's own *_tool / *_config modules are imported by flat name
out = {}
for rel in files:
    name = os.path.splitext(os.path.basename(rel))[0]
    code = [l for l in open(os.path.join(layer, rel), encoding="utf-8", errors="replace").read().splitlines() if l.strip() and not l.strip().startswith("#")]
    try:
        spec = importlib.util.spec_from_file_location("probe_" + rel.replace("/", "_").replace(".py", ""), os.path.join(layer, rel))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        out[rel] = ["STUB" if len(code) <= 3 else "OK", ""]
    except BaseException as e:
        out[rel] = ["IMPORT_ERROR", "%s: %s" % (type(e).__name__, str(e)[:120])]
print("@@" + json.dumps(out))
'''


def layer_files(layer):
    base = os.path.join(ROOT, layer)
    files = []
    if layer == "lib":
        return [f for f in sorted(os.listdir(base)) if f.endswith(".py") and f not in SKIP]
    for sub in ("", "lib", "config"):
        d = os.path.join(base, sub)
        if os.path.isdir(d):
            files += [os.path.join(sub, f).replace("\\", "/") if sub else f for f in sorted(os.listdir(d)) if f.endswith(".py") and f not in SKIP]
    return files


def check(layer):
    files = layer_files(layer)
    r = subprocess.run([sys.executable, "-c", "import importlib.util\n" + PROBE, os.path.join(ROOT, layer), ROOT, json.dumps(files)], cwd=ROOT,
                       capture_output=True, text=True, timeout=180, env=dict(os.environ, NEXXUS_MESH_URL="http://127.0.0.1:9", PYTHONDONTWRITEBYTECODE="1"))
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@")), None)
    return json.loads(line[2:]) if line else {"<probe>": ["PROBE_FAILED", (r.stderr.strip().splitlines() or ["no output"])[-1][:120]]}


def main():
    bad = 0
    for layer in LAYERS:
        res = check(layer)
        counts = {}
        for st, _ in res.values():
            counts[st] = counts.get(st, 0) + 1
        broke = {k: v for k, v in res.items() if v[0] in ("IMPORT_ERROR", "PROBE_FAILED")}
        bad += len(broke)
        print("%-18s %s" % (layer, "  ".join("%s %d" % (k, v) for k, v in sorted(counts.items()))))
        for k, (st, why) in sorted(broke.items()):
            print("    %-13s %s  %s" % (st, k, why))
    print("\n%s" % ("ALL MODULES IMPORT" if not bad else "%d problem(s)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
