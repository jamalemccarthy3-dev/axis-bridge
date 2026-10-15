# src/life_cycle_policy_config.py
class LifeCyclePolicyConfig:
    def __init__(self):
        # Time-based thresholds for asset governance
        self.archive_threshold_days = 30  # Move to archive after 30 days
        self.deletion_threshold_days = 90 # Purge permanently after 90 days
        self.enforce_policy = True