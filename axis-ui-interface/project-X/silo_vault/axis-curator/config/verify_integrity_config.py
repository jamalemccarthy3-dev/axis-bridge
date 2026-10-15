# src/verify_integrity_config.py
class VerifyIntegrityConfig:
    def __init__(self):
        # The master manifest mapping file paths to their expected hashes
        self.manifest = {
            "data/core_logic.bin": "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
            "data/user_profile.dat": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        }