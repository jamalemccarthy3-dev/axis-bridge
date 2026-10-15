# src/checksum_verification_utility.py
import hashlib
import logging

class ChecksumVerificationEngine:
    def __init__(self, config):
        self.algorithm = config.algorithm
        self.logger = logging.getLogger("Factory.Curator.Checksum")

    def verify_hash(self, file_path, expected_hash):
        """Calculates the cryptographic hash of a file and compares it to the expected value."""
        try:
            # Initialize the specified hashing algorithm
            hasher = hashlib.new(self.algorithm)
            
            # Read file in chunks to handle large files efficiently
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            
            calculated_hash = hasher.hexdigest()
            
            if calculated_hash == expected_hash:
                self.logger.info(f"Checksum match for: {file_path}")
                return {"status": "intact", "calculated": calculated_hash, "code": 200}
            else:
                self.logger.warning(f"Checksum mismatch for: {file_path}")
                return {"status": "mismatch", "calculated": calculated_hash, "code": 403}
                
        except Exception as e:
            self.logger.error(f"Checksum engine failure: {e}")
            return {"status": "error", "message": str(e), "code": 500}