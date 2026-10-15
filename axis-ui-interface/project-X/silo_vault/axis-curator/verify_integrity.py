# src/verify_integrity_utility.py
import hashlib
import logging
import os

class VerifyIntegrityEngine:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("Factory.Curator.Verify")

    def scan_file(self, file_path):
        """Performs actual SHA-256 cryptographic verification."""
        if not os.path.exists(file_path):
            self.logger.error(f"File missing: {file_path}")
            return {"status": "error", "code": 404}

        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            calculated_hash = sha256_hash.hexdigest()
            # Compares against the manifest provided in config. A file the manifest does not know cannot be called corrupted or verified.
            expected = self.config.manifest.get(file_path)
            if expected is None:
                self.logger.warning(f"Not in the manifest: {file_path}")
                return {"status": "not_in_manifest", "code": 404}
            if calculated_hash == expected:
                self.logger.info(f"Integrity verified: {file_path}")
                return {"status": "verified", "code": 200}
            else:
                self.logger.warning(f"CORRUPTION DETECTED: {file_path}")
                return {"status": "corrupted", "code": 403}
        except Exception as e:
            self.logger.critical(f"Verification engine failure: {e}")
            return {"status": "system_error", "code": 500}