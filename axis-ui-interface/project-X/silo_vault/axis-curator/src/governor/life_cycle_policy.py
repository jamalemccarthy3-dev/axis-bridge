# src/life_cycle_policy_utility.py
import time
import os
import logging

class LifeCyclePolicyEngine:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("Factory.Governance.LifeCycle")

    def evaluate_asset(self, file_path):
        """Determines the current lifecycle stage of an asset."""
        try:
            file_age_days = (time.time() - os.path.getmtime(file_path)) / 86400
            
            if file_age_days > self.config.archive_threshold_days:
                return {"status": "transition", "target_state": "archive", "code": 200}
            elif file_age_days > self.config.deletion_threshold_days:
                return {"status": "transition", "target_state": "purge", "code": 200}
            
            return {"status": "active", "target_state": "none", "code": 200}
        except Exception as e:
            self.logger.error(f"Policy evaluation failure: {e}")
            return {"status": "error", "code": 500}