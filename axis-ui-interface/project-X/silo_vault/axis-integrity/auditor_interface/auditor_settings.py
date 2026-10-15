# AUDITOR_SETTINGS: The Control Panel Brain
# Purpose: Manages the system's operational state.
import auditor_settings_tool as tool


def toggle_mode(new_mode):
    """Switches the auditor to LIVE, MAINTENANCE or LOCKDOWN and returns the settings now in force. An unknown mode raises ValueError and changes nothing."""
    return tool.apply_settings(new_mode)
