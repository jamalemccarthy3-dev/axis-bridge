# ALERT_REGISTRY_CONFIG: Registry Bounds
# Purpose: Define alert severity and priority levels.
import os

import paths_config

SEVERITIES = ("INFO", "WARNING", "CRITICAL")
DEFAULT_SEVERITY = "INFO"
MAX_ACTIVE_ALERTS = 50       # the newest 50 alerts that are still open; older ones stay in the ledger
CLEAR_ON_FREEZE = True
ALERTS_FILE = os.path.join(paths_config.LOGS, "alerts.jsonl")
