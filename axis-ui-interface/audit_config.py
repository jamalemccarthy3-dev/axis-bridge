# Final Copy: The Audit Configuration
class AuditConfig:
    def get_audit_settings(self):
        """Defines what level of data is recorded."""
        return {
            "logging_level": "VERBOSE",
            "encryption": "AES_SOVEREIGN"
        }