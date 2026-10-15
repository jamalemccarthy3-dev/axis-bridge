# SILO_INVENTORY_MAP_UTILITY: The Registry v1.0
# District: Auditor/Registry
# Purpose: Brain that verifies system health via the map.

import ledger
import silo_inventory_map_tool as tool


def verify_district(silo_id):
    # The Brain checks the registry before allowing a request: only engines that are in the baseline and present are authorised
    ok = silo_id in tool.baseline() and silo_id in tool.get_full_map()
    if ok:
        print(f"[BRAIN] Registry: {silo_id} verified as authorized.")
    else:
        ledger.record_event("UNAUTHORIZED_DISTRICT", str(silo_id))
    return ok


def request_inventory_snapshot(auditor_id, auth_token):
    """The Auditor's request for the system map. Needs a valid token for that auditor persona; without one NOTHING is revealed.
    -> {"authorized": True, "new", "missing", "engines": [...present...], "baseline": [...]} or {"authorized": False}."""
    import auth_protocol
    if not auth_protocol.authorize_request(auth_token, auditor_id):
        return {"authorized": False}
    d = check_inventory()
    return {"authorized": True, "new": d["new"], "missing": d["missing"], "engines": sorted(tool.get_full_map()), "baseline": sorted(tool.baseline())}


def check_inventory():
    """-> {"new", "missing"}: engines that appeared or vanished since the baseline. Each is recorded."""
    d = tool.diff()
    for e in d["new"]:
        ledger.record_event("ENGINE_APPEARED", e)
    for e in d["missing"]:
        ledger.record_event("ENGINE_VANISHED", e)
    return d
