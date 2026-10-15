# src/optimize_storage_config.py
import os

class OptimizeStorageConfig:
    def __init__(self):
        # The specific directory designated for storage optimization
        self.archive_dir = os.path.join(os.getcwd(), "data", "archive")
        
        # Ensure the directory exists upon initialization
        if not os.path.exists(self.archive_dir):
            os.makedirs(self.archive_dir)