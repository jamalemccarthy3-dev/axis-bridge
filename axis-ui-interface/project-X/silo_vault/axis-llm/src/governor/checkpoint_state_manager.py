import json
import os
import shutil
import logging
from datetime import datetime
from src.governor.config.checkpoint_state_manager_config import CheckpointStateConfig

class CheckpointStateManager:
    def __init__(self, config=None):
        self.config = config or CheckpointStateConfig()
        self.logger = logging.getLogger("Factory.Checkpoint")

    def create_snapshot(self, system_state):
        """Writes current system state to a secure checkpoint file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"checkpoint_{timestamp}.json"
            filepath = os.path.join(self.config.checkpoint_dir, filename)

            with open(filepath, 'w') as f:
                json.dump(system_state, f, indent=4)

            self.logger.info(f"Checkpoint created: {filepath}")
            return filepath
        except Exception as e:
            self.logger.critical(f"Failed to create checkpoint: {e}")
            return None

    def load_snapshot(self, checkpoint_id):
        """Restores the system state from a specific checkpoint."""
        filepath = os.path.join(self.config.checkpoint_dir, checkpoint_id)
        if not os.path.exists(filepath):
            self.logger.error(f"Checkpoint {checkpoint_id} not found.")
            return None
        
        with open(filepath, 'r') as f:
            return json.load(f)