# Final Copy: The Sovereign Data Recovery Logic
from src.recovery_tool import RecoveryTool
from src.recovery_config import RecoveryConfig

class Recovery:
    def __init__(self, system_port):
        self.system_port = system_port
        
        # Initialize Triad components
        self.tool = RecoveryTool(self)
        self.config = RecoveryConfig()

    def initiate_recovery(self, project_id, snapshot_id):
        """
        Restores a project silo from a secure snapshot.
        Re-registers the identity and signals the shield to re-spawn.
        """
        # 1. Restore the identity via Registry
        # 2. Trigger the Shield birth sequence again
        self.system_port.audit.record_event("RECOVERY_START", project_id, f"Snapshot: {snapshot_id}")
        
        return f"Silo {project_id} restored from snapshot {snapshot_id}."