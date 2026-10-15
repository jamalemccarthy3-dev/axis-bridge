# Final Copy: The Recovery Configuration
class RecoveryConfig:
    def get_recovery_policy(self):
        """Sets the backup frequency and storage location."""
        return {
            "snapshot_retention": "30_DAYS",
            "auto_restore": False
        }