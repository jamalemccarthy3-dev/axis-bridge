# BRIDGE: The Bridge Brain
# Purpose: The gatekeeper for all transit operations. The Auditor calls this.

import bridge_config as config
import bridge_tool as tool

def initiate_transit(data, destination, auth_token):
    """Moves data to a silo through process -> deliver -> purge, but only when the bridge is ACTIVE, the engine is not halted, and `auth_token` is valid for the persona 'bridge'.
    -> the bridge sequence result, or {"status": "BRIDGE_OFFLINE" | "HALTED" | "UNAUTHORIZED"}."""
    if config.BRIDGE_STATUS != "ACTIVE":
        return {"status": "BRIDGE_OFFLINE"}
    from lib.layers import load
    import integrity_store
    if (integrity_store.read_json("halt.json", {}) or {}).get("halted"):
        return {"status": "HALTED"}
    if not load("auditor_interface", "validator").validate_access("bridge", auth_token):
        return {"status": "UNAUTHORIZED"}
    return tool.run_bridge_sequence(data, destination)
