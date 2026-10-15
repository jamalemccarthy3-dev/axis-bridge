# SILO_INVENTORY_MAP_CONFIG: The Registry v1.0
# District: Auditor/Registry
# Purpose: Define the map schema. The set of engines that are ALLOWED to exist is a baseline file the auditor writes the first time it looks
# (and only a person should change afterwards): an engine that appears or vanishes later is a finding.
import os

import paths_config

REGISTRY_ENABLED = True
LOG_MAP_UPDATES = True
BASELINE_FILE = os.path.join(paths_config.LOGS, "inventory_baseline.json")
