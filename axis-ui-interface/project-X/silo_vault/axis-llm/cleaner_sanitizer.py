import re
import logging
from config.cleaner_sanitizer_config import CleanerSanitizerConfig

class CleanerSanitizerEngine:
    def __init__(self, config=None):
        self.config = config or CleanerSanitizerConfig()
        self.logger = logging.getLogger("Factory.Sanitizer")

    def scrub(self, raw_data):
        # Executes the full sanitization pipeline.
        if not raw_data:
            return ""
        
        # 1. Block prohibited patterns (Security/Injection prevention)
        for pattern in self.config.blacklist:
            if re.search(pattern, raw_data):
                self.logger.warning(f"Prohibited pattern detected: {pattern}")
                return None

        # 2. Enforce length constraints
        if len(raw_data) > self.config.max_length:
            self.logger.warning("Input truncated due to length constraint.")
            raw_data = raw_data[:self.config.max_length]

        # 3. Clean noise while preserving essential structure
        sanitized = re.sub(r'[^a-zA-Z0-9\s.,?!]', '', raw_data)
        return sanitized.strip()