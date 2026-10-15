# LEDGER_CONFIG: Memory Laws
# Purpose: Define log storage and access restrictions.
import os

import paths_config

LOG_FILE_PATH = os.path.join(paths_config.LOGS, "system.ledger.jsonl")
APPEND_ONLY = True
TAMPER_EVIDENT = True        # every entry carries the hash of the one before it (lib/auditor.py): an edit, removal or reorder is detected
ENCRYPTION_REQUIRED = False  # the ledger is tamper-EVIDENT, not encrypted: anyone who can read the file can read the entries
