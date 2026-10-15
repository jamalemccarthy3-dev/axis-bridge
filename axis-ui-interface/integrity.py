# Final Copy: Pipeline Integrity Logic
from integrity_tool import IntegrityTool
from integrity_config import IntegrityConfig

class Integrity:
    def __init__(self, system_port, registry, shield):
        self.system_port = system_port
        self.registry = registry
        self.shield = shield
        
        # Initialize Triad components
        self.tool = IntegrityTool(self)
        self.config = IntegrityConfig()

    def check_system_state(self, project_id):
        """Verifies the status of all pipeline components."""
        is_registered = self.registry.tool.verify_identity(project_id)
        is_shielded = self.shield.tool.validate_connection()
        
        return is_registered and is_shielded
