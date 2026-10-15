# SYSTEM_CLOCK_UTILITY: The Heartbeat v1.0
# District: Auditor/Core
# Purpose: Orchestrates time-stamping for the Forensics/Ledger.

import system_clock_tool as tool

def get_formatted_time():
    # The Brain decides how the time is formatted for the Ledger
    timestamp = tool.get_current_timestamp()
    return f"[{timestamp}]"
