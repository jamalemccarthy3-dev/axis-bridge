# ALERT_REGISTRY: The Registry Brain
# Purpose: Orchestrates alert categorization and triggers responses.

import alert_registry_tool as tool
import ledger


def register_new_alert(msg, severity):
    # The Brain decides how to categorize and dispatch the alert; every alert is also written to the ledger
    alert = tool.store_alert({"msg": msg, "severity": severity})
    ledger.record_event("ALERT_" + alert["severity"], msg)
    return alert
