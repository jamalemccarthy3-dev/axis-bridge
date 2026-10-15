# Final Copy: The Validation Configuration
class ValidateConfig:
    def get_validation_rules(self):
        """Sets the strictness of the processor's input filters."""
        return {
            "strict_mode": True,
            "required_fields": ["header", "payload", "timestamp"]
        }
