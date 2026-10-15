# GOVERNANCE: The Authority Brain
# Purpose: Evaluates system state against the Constitution and mandates action.

import alert_registry
import governance_tool as tool
import ledger


def evaluate_compliance(event_data):
    """event_data: {"severity", "silo_id", "message"}. A CRITICAL event is recorded, alerted and a freeze is recommended; anything else is recorded.
    -> {"action": ..., "freeze": ...}"""
    sev, silo = str(event_data.get("severity", "INFO")).upper(), event_data.get("silo_id")
    msg = event_data.get("message", "")
    ledger.record_event("GOVERNANCE_" + sev, "%s: %s" % (silo, msg))
    if sev == "CRITICAL":
        alert_registry.register_new_alert("%s: %s" % (silo, msg), "CRITICAL")
        freeze = tool.apply_freeze(silo)
        ledger.record_event("FREEZE_RECOMMENDED", str(silo))
        return {"action": "VIOLATION_RECORDED_FREEZE_RECOMMENDED", "freeze": freeze}
    return {"action": "RECORDED", "freeze": None}
