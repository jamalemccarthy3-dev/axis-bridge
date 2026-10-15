# src/automated_metadata_tagging_config.py
class AutomatedMetadataTaggingConfig:
    def __init__(self):
        # Default policy for automated asset labeling
        self.default_priority = "standard"
        self.include_system_stats = True
        self.enforce_schema = "v1_core"