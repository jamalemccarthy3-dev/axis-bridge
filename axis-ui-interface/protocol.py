# Final Copy: The Homecoming Handshake Logic
from protocol_tool import ProtocolTool
from protocol_config import ProtocolConfig
from shield import Shield

class Protocol:
    def __init__(self, system_port, registry):
        self.system_port = system_port
        self.registry = registry
        
        # Initialize Triad components
        self.tool = ProtocolTool(self)
        self.config = ProtocolConfig()

    def execute_handshake(self, project_id, silo_path):
        """Orchestrates the birth: Register -> Shield -> Spawn."""
        if self.registry.register_silo(project_id, silo_path):
            # Instantiate Shield which automatically triggers Birth Sequence
            new_shield = Shield(project_id, self.system_port)
            return True
        return False

