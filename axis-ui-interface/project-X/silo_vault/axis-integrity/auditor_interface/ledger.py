# LEDGER: The Memory Brain
# Purpose: Formats audit entries and enforces memory integrity.

import ledger_tool as tool


def record_event(event_type, description):
    # Formats the event before handing it to the tool
    entry = f"EVENT: {event_type} | DESC: {description}"
    return tool.write_to_disk(entry)


def verify():
    return tool.verify()
