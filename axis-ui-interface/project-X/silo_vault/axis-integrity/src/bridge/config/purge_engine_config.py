
# PURGE_ENGINE_CONFIG: Sanitation Parameters
# Purpose: Defines the strict rules for how and when the Bridge is scrubbed.

# Determines if the buffer is cleared immediately or on a timer
PURGE_ON_TRANSFER_COMPLETE = True
BUFFER_RETENTION_MS = 0  # Zero-retention for maximum sovereignty
SECURE_WIPE_ENABLED = True # Overwrites memory addresses, doesn't just delete
