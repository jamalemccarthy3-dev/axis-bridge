import os

class CheckpointStateConfig:
    def __init__(self):
        # Pointing to the secure storage area on your drive
        self.checkpoint_dir = os.path.join(os.getcwd(), "data", "checkpoints")
        self.max_retention = 10
        self.auto_save_interval = 3600 # seconds

        # Ensure the directory exists
        if not os.path.exists(self.checkpoint_dir):
            os.makedirs(self.checkpoint_dir)