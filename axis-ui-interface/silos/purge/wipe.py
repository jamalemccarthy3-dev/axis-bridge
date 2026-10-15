# Final Copy: The Sovereign Purge Logic
from src.wipe_tool import WipeTool
from src.wipe_config import WipeConfig

class Wipe:
    def __init__(self, system_port):
        self.system_port = system_port
        
        # Initialize Triad components
        self.tool = WipeTool(self)
        self.config = WipeConfig()

    def execute_purge(self, project_id):
        """
        Executes a hard wipe on a specific silo.
        Signals the Port to purge the UI assets and clear the Registry.
        """
        # 1. Purge the visual bubble via actuator
        self.system_port.actuator.purge_bubble(project_id)
        
        # 2. Clear registry entry
        if project_id in self.system_port.registry.registered_silos:
            del self.system_port.registry.registered_silos[project_id]
            
        return f"Silo {project_id} successfully purged."
