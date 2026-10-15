"""
public_facade/capture_receipts.py - captures the "proof of life" receipts for the public README from REAL runs. Nothing here is typed by hand:
every line is produced from the live system or from a fresh test run, and the capture ABORTS (writes nothing) if anything failed.

  Receipt 1  live multi-engine synchronisation: the running system's own mesh telemetry (one machine, no cloud)
  Receipt 2  autonomous pipeline orchestration + guardian: the master suites, run now, totals only

What never goes in: source code, file names, paths, ports, host or user names, per-check names (they would describe internals), the
consultant network, or anything about how engines are wired. Only engine folder names (already public) and PASS/FAIL results.
    python capture_receipts.py        (needs the NEXXUS server running on this machine)
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
PX = WORK / "axis-ui-interface" / "project-X"
OUT = HERE / "receipts.md"
SUITES = [  # (public title, script, working dir, regex that yields "passed/total")
    ("Guardian: signing, replay, tamper and drift refusal", PX / "axis_gate" / "test_axis_gate.py", PX / "axis_gate"),
    ("Scoped key custody and grants", PX / "axis_gate" / "test_key_grants.py", PX / "axis_gate"),
    ("Human-approved autonomous tool intake", PX / "silo_vault" / "nexxus" / "test_tool_ingest.py", PX / "silo_vault" / "nexxus"),
    ("Dependency and key provisioning loop", PX / "silo_vault" / "nexxus" / "test_tool_provision.py", PX / "silo_vault" / "nexxus"),
    ("Background job pipeline orchestration", PX / "silo_vault" / "nexxus" / "test_job_manager.py", PX / "silo_vault" / "nexxus"),
    ("Zero-cloud dashboard: no external loads, bundled 3D library", PX / "silo_vault" / "nexxus" / "test_dashboard_offline.py", PX / "silo_vault" / "nexxus"),
    ("Public-facade leak guard", HERE / "test_facade_guard.py", HERE),
]


def get(path):
    return json.load(urllib.request.urlopen("http://localhost:8000" + path, timeout=60))


def receipt_mesh():
    tele = get("/api/mesh/telemetry")["engines"]
    man = get("/api/mesh/manifest")
    gate = get("/api/gate/status")["gate"]
    names = sorted(tele, key=str.lower)
    dead = [n for n in names if not tele[n].get("live")]
    if dead or man["engines_verified"] != man["expected_engines"] or man["engines_mesh_ready"] != man["expected_engines"]:
        raise SystemExit("ABORT: the mesh is not fully live/verified (%s). Nothing was written." % (dead or "manifest mismatch"))
    w = max(len(n) for n in names)
    lines = ["%s  signed heartbeat verified   LIVE" % ("[PASS] " + n.ljust(w)) for n in names]
    lines += ["", "COMPONENTS LIVE        %d / %d" % (len(names) - len(dead), len(names)),
              "MANIFEST VERIFIED     %d / %d" % (man["engines_verified"], man["expected_engines"]),
              "MESH-ENABLED          %d / %d" % (man["engines_mesh_ready"], man["expected_engines"]),
              "PACKETS VERIFIED      %d" % gate["allowed_total"],
              "PACKETS REFUSED       %d" % gate["blocked_total"],
              "GUARDIAN STATE        %s" % ("CLEAR" if gate["ok"] else "ATTENTION")]
    if not gate["ok"]:
        raise SystemExit("ABORT: the guardian reports a problem. Nothing was written.")
    return lines


def run_suite(title, script, cwd):
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEXXUS_")}
    r = subprocess.run([sys.executable, str(script)], cwd=str(cwd), env=env, capture_output=True, text=True, timeout=900)
    text = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"(\d+)\s*/\s*(\d+)\s+(?:checks\s+)?passed", text)
    if not m or r.returncode != 0 or m.group(1) != m.group(2):
        raise SystemExit("ABORT: suite failed or unreadable: %s (exit %s). Nothing was written." % (title, r.returncode))
    return int(m.group(1)), int(m.group(2))


def receipt_suites():
    rows, passed, total = [], 0, 0
    w = max(len(t) for t, _, _ in SUITES)
    for title, script, cwd in SUITES:
        p, t = run_suite(title, script, cwd)
        passed += p; total += t
        rows.append("[PASS] %s  %3d / %-3d" % (title.ljust(w), p, t))
    rows += ["", "CHECKS PASSED         %d / %d" % (passed, total), "CHECKS FAILED         %d" % (total - passed), "RESULT                ALL GREEN"]
    return rows


def main():
    stamp = time.strftime("%Y-%m-%d %H:%M")
    r1, r2 = receipt_mesh(), receipt_suites()
    md = ["<!-- generated from real runs; do not edit by hand -->", "",
          "**Receipt 1 - live multi-engine synchronisation.** Captured from the running reference build on a single local machine.", "", "```", "NEXXUS MESH  -  proof of life  -  captured " + stamp] + [""] + r1 + ["```", "",
          "**Receipt 2 - autonomous pipeline orchestration and guardian.** The master suites, run fresh against the reference build for this capture.", "", "```", "NEXXUS MASTER SUITES  -  captured " + stamp] + [""] + r2 + ["```", ""]
    OUT.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
