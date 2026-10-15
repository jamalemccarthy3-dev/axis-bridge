# src/optimize_storage_utility.py
import os
import shutil
import logging

class OptimizeStorageEngine:
    def __init__(self, config):
        self.archive_dir = config.archive_dir
        self.logger = logging.getLogger("Factory.Curator.Optimizer")

    def run_disk_optimization(self):
        """Performs actual directory cleanup and redundancy pruning."""
        try:
            purged_count = 0
            # Actively scan and remove temp files defined in config
            for filename in os.listdir(self.archive_dir):
                if filename.startswith("tmp_") or filename.endswith(".bak"):
                    file_path = os.path.join(self.archive_dir, filename)
                    os.remove(file_path)
                    purged_count += 1
                    self.logger.info(f"Purged temporary asset: {filename}")
            
            return {"status": "optimized", "items_removed": purged_count, "code": 200}
        except Exception as e:
            self.logger.critical(f"Storage optimization failure: {e}")
            return {"status": "error", "message": str(e), "code": 500}