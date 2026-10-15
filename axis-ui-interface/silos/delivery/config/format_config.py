# Final Copy: The Format Configuration
class FormatConfig:
    def get_format_rules(self):
        """Sets the required encoding and schema standards."""
        return {
            "encoding": "UTF-8",
            "schema_version": "2.0",
            "checksum_required": True
        }