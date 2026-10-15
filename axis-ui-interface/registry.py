# Final Copy: The Silo Identity Registry Logic
from registry_tool import RegistryTool
from registry_config import RegistryConfig

class Registry:
    def __init__(self, system_port):
        self.system_port = system_port
        self.registered_silos = {}
        
        # Initialize Triad components
        self.tool = RegistryTool(self)
        self.config = RegistryConfig()

    def register_silo(self, project_id, silo_path):
        """Authenticates and binds the silo to the Port."""
        if project_id not in self.registered_silos:
            self.registered_silos[project_id] = {
                "path": silo_path,
                "status": "REGISTERED"
            }
            # Acknowledge to Port
            self.system_port.acknowledge_registry(project_id)
            return True
        return False