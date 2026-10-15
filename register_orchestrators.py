"""register_orchestrators.py - one-time (and safe to repeat) setup: tells the NEXXUS orchestrator bus which orchestrator is the ONLY door into each engine,
and which engines may act as independent quality-control reviewers.

Run it once the server is up, with the admin token in the environment:
    call nexxus_admin.bat            (sets NEXXUS_ADMIN_TOKEN for this window)
    python register_orchestrators.py
Edit ORCHESTRATORS below to add engines. An engine that builds something must NOT be its only reviewer: the bus refuses a builder grading itself.
"""
import json
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("NEXXUS_MESH_URL", "http://127.0.0.1:8000").rstrip("/")

# engine name -> (orchestrator id, may issue QC verdicts, receives the audit feed)
ORCHESTRATORS = {
    "axis-SandM": ("sandm.governor", False, False),
    "axis-video_creator": ("video_creator.governor", False, False),
    "axis-curator": ("curator.governor", True, False),         # the curator checks integrity and checksums: a natural independent reviewer
    "axis-core": ("core.governor", False, False),              # the switchboard: reports its security and purge actions to the auditor
    "axis-integrity": ("integrity.governor", False, True),     # the auditor: receives every engine's audit reports into its tamper-evident chain
}


def post(path, body, token):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "X-Nexxus-Admin-Token": token}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def main():
    token = os.environ.get("NEXXUS_ADMIN_TOKEN", "")
    if not token:
        print("NEXXUS_ADMIN_TOKEN is not set in this window (run: call nexxus_admin.bat).")
        return 2
    bad = 0
    for engine, (orch, qc, aud) in ORCHESTRATORS.items():
        r = post("/api/bus/register", {"engine": engine, "orchestrator": orch, "qc_reviewer": qc, "auditor": aud}, token)
        ok = r.get("status") == "success"
        bad += 0 if ok else 1
        print("%-20s %-24s %s%s" % (engine, orch, "registered" if ok else "FAILED: %s" % r.get("message"), ("  (QC reviewer)" if ok and qc else "") + ("  (auditor)" if ok and aud else "")))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
