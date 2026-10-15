# FORENSICS_CONFIG: Evidence Packaging
# Purpose: Define the format and sensitivity of forensic data.

EVIDENCE_FORMAT = "JSON_HASHED"       # plain JSON carrying its own SHA-256; the dump chains the hashes
AUTO_PURGE_AFTER_DUMP = True  # Ensures the hand-off is clean
