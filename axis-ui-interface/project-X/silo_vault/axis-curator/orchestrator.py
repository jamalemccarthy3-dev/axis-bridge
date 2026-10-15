"""orchestrator.py - axis-curator's orchestrator, acting as the INDEPENDENT quality-control reviewer on the orchestrator bus.

For every build another engine reports, it re-checks the real artifact with its own tools and returns a verdict:
  critical (verdict = fail): the file is missing or empty; its SHA-256 differs from what was reported; a .json file does not parse;
                             a storyboard whose scene count or timings do not match the script in the order
  warning  (verdict = pass, but listed): markup or interference markers in the text
It never builds anything and never reviews its own work (the bus refuses that anyway).

Run:  python orchestrator.py --once      (one round)      python orchestrator.py --serve      (keep listening)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bootstrap  # noqa: E402,F401
from checksum_verification_tool import ChecksumVerificationTool  # noqa: E402
from denoising_sanitization_tool import DenoisingSanitizationTool  # noqa: E402
from nexxus_link import client  # noqa: E402


def _sentences(text):
    return [p for p in re.split(r"(?<=[.!?])\s+|\n+", str(text or "").strip()) if p.strip()]


def review(order):
    """-> (verdict, findings, sha256 of the artifact as it is NOW)"""
    path, findings = order.get("artifact"), []

    def crit(msg):
        findings.append({"severity": "critical", "message": msg})

    if not path or not os.path.isfile(path):
        crit("the artifact is missing")
        return "fail", findings, None
    if os.path.getsize(path) == 0:
        crit("the artifact is empty")
    check = ChecksumVerificationTool().execute(path, order.get("artifact_sha256") or "")
    sha = check.get("calculated")
    if check.get("status") != "intact":
        crit("the file's SHA-256 does not match what the builder reported")
    text = None
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        findings.append({"severity": "info", "message": "binary file: content checks skipped"})
    if text is not None and path.lower().endswith(".json"):
        try:
            data = json.loads(text)
        except ValueError as e:
            crit("the JSON does not parse: %s" % e)
            data = None
        spec = order.get("spec") or {}
        if data is not None and spec.get("kind") == "storyboard":
            scenes = data.get("scenes") or []
            expected = len(_sentences(spec.get("script")))
            if len(scenes) != expected:
                crit("the storyboard has %d scenes but the script has %d sentences" % (len(scenes), expected))
            if any(s.get("duration_s", 0) <= 0 for s in scenes):
                crit("a scene has no duration")
            if scenes and abs(sum(s["duration_s"] for s in scenes) - data.get("total_s", -1)) > 0.05:
                crit("the scene durations do not add up to total_s")
            starts_ok = all(abs(scenes[i]["start_s"] + scenes[i]["duration_s"] - scenes[i + 1]["start_s"]) <= 0.05 for i in range(len(scenes) - 1))
            if not starts_ok:
                crit("scenes overlap or leave gaps")
    if text is not None:
        cleaned = DenoisingSanitizationTool().process(text)
        if "<" in text and cleaned["removed_chars"] > 0 and re.search(r"<[a-zA-Z/][^>]*>", text):
            findings.append({"severity": "warning", "message": "the text contains markup"})
        if "noise_artifact" in text:
            findings.append({"severity": "warning", "message": "interference markers found in the text"})
    return ("fail" if any(f["severity"] == "critical" for f in findings) else "pass"), findings, sha


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
    import orchestrator_worker
    link = client()
    if "--serve" in sys.argv:
        orchestrator_worker.serve(link, review=review)
    else:
        for d in orchestrator_worker.run_once(link, review=review):
            print(d["action"], d["order"], d["result"].get("status"), d["result"].get("message", ""))
