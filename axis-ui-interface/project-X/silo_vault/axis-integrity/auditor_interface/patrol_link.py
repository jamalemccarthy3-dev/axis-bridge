# PATROL_LINK: The Monitor Brain
# Purpose: Orchestrates the patrol and logs anomalies to the Auditor.

import alert_registry
import ledger
import patrol_link_config as config
import patrol_link_tool as tool


def start_patrol(now=None):
    """Checks every target silo once. -> the list of results; every silo that is not alive is recorded and alerted."""
    results = []
    for silo in tool.list_silos():
        status = tool.ping_silo(silo, now)
        results.append(status)
        if not status["alive"]:
            ledger.record_event("SILO_NOT_ALIVE", "%s: %s" % (silo, status["reason"]))
            alert_registry.register_new_alert("%s is not responsive: %s" % (silo, status["reason"]), "WARNING")
    return results
