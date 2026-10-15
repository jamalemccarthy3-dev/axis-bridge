# Final Copy: Sovereign Silo Synchronization Logic
from src.processor.sync_tool import SyncTool
from src.processor.sync_config import SyncConfig

class Sync:
    def __init__(self, processor_port):
        self.processor_port = processor_port
        
        # Initialize Triad components
        self.tool = SyncTool(self)
        self.config = SyncConfig()

    def synchronize_state(self, current_state):
        """
        Forces alignment between local silo state and the Port's master state.
        """
        success = self.tool.push_to_registry(current_state)
        if success:
            self.processor_port.audit.record_event("SYNC_SUCCESS", "SILO_CORE", "Alignment achieved.")
        return success
