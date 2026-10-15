# src/checksum_verification_config.py
class ChecksumConfig:
    def __init__(self):
        # Standardizing on SHA-256 for cryptographic integrity
        self.algorithm = "sha256"