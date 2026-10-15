# src/automated_metadata_tagging_utility.py
import os
import datetime
import logging

class AutomatedMetadataTaggingEngine:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("Factory.Curator.Metadata")

    def generate_tags(self, file_path):
        """Extracts file attributes and generates systemic metadata tags."""
        try:
            if not os.path.exists(file_path):
                return {"status": "error", "code": 404}

            stats = os.stat(file_path)
            tags = {
                "created_at": datetime.datetime.fromtimestamp(stats.st_ctime).isoformat(),
                "size_kb": round(stats.st_size / 1024, 2),
                "extension": os.path.splitext(file_path)[1],
                "priority": self.config.default_priority
            }
            
            self.logger.info(f"Metadata generated for: {file_path}")
            return {"status": "success", "metadata": tags, "code": 200}
        except Exception as e:
            self.logger.error(f"Metadata tagging failure: {e}")
            return {"status": "error", "message": str(e), "code": 500}