# FREEZE_ALL: The Emergency Brain
# Purpose: Coordinates the emergency shutdown sequence.

import freeze_all_tool as tool
import ledger


def trigger_emergency_lockdown():
    # The Brain handles the story of the lockdown: it is written to the ledger first, then requested
    ledger.record_event("EMERGENCY_FREEZE_REQUESTED", "system-wide")
    print("[BRAIN] EMERGENCY SIGNAL RECEIVED. Freeze requested from NEXXUS (not performed here).")
    return tool.execute_hard_stop()
