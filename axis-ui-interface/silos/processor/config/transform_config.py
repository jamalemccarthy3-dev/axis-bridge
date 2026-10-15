# Final Copy: The Transformation Configuration
class TransformConfig:
    def get_transform_settings(self):
        """Defines the transformation mapping rules."""
        return {
            "mapping_mode": "STRICT_PATH",
            "log_mapping_errors": True
        }
