# Final Copy: The Scrub Configuration
class ScrubConfig:
    def get_scrub_depth(self):
        """Sets the depth of the data cleaning process."""
        return {
            "cache_depth": "FULL",
            "log_persistence": "MINIMAL"
        }