# AUDITOR: The Sovereign Brain
# Purpose: Imports all Triad modules and orchestrates system integrity.

import alert_registry
import auditor_tool as tool
import governance
import ledger
import patrol_link
import silo_inventory_map


def run_sentinel_cycle(reporter=None, now=None):
    """The Brain's master loop, once:
    1. patrol: is every engine present and showing a pulse?
    2. inventory: did an engine appear or vanish since the baseline?
    3. governance: every CRITICAL finding is recorded, alerted and a freeze is recommended
    4. ledger: is the audit chain still intact?
    5. report: every finding is also sent to NEXXUS (reporter(kind, detail)), whose ledger the auditor does not control
    -> a report dict. The auditor watches and tells; it never changes another engine."""
    findings = []
    patrol = patrol_link.start_patrol(now)
    for p in patrol:
        if not p["alive"]:
            findings.append({"severity": "WARNING", "silo": p["silo"], "message": "not alive: %s" % p["reason"]})
    inv = silo_inventory_map.check_inventory()
    for e in inv["new"]:
        findings.append({"severity": "CRITICAL", "silo": e, "message": "an engine that is not in the baseline has appeared"})
    for e in inv["missing"]:
        findings.append({"severity": "CRITICAL", "silo": e, "message": "an engine from the baseline has vanished"})
    for f in findings:
        if f["severity"] == "CRITICAL":
            governance.evaluate_compliance({"severity": "CRITICAL", "silo_id": f["silo"], "message": f["message"]})
    ok, info = ledger.verify()
    if not ok:
        findings.append({"severity": "CRITICAL", "silo": "axis-integrity", "message": "the audit ledger has been tampered with (first bad entry %s)" % info})
        tool.trigger_global_alert("ledger tampered at entry %s" % info)
    reported = 0
    if reporter is not None:
        for f in findings:
            try:
                reporter("SENTINEL_" + f["severity"], "%s: %s" % (f["silo"], f["message"]))
                reported += 1
            except Exception:
                pass
    print("[BRAIN] Sentinel cycle done: %d silo(s) patrolled, %d finding(s)." % (len(patrol), len(findings)))
    return {"patrolled": len(patrol), "alive": sum(1 for p in patrol if p["alive"]), "inventory": inv, "findings": findings, "ledger_ok": ok, "reported_to_nexxus": reported}
