# PURGE_ENGINE: The Sanitation Brain
# Purpose: Orchestrates the wipe process and confirms it to the system.
import purge_engine_tool as tool


def initiate_sanitation(buffer_id):
    """Wipes the buffer and reports what was wiped. -> {"status": "CLEAN", "buffer", "wiped", "bytes", "secure"} or {"status": "ERROR", "reason"} (a bad name or a file that cannot be wiped)."""
    try:
        r = tool.wipe_buffer(buffer_id)
    except (OSError, ValueError) as e:
        return {"status": "ERROR", "reason": "WIPE_FAILED: %s" % e}
    return dict(r, status="CLEAN", buffer=buffer_id)
