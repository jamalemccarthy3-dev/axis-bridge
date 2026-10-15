# Final Copy: The Sovereign Barrier Logic
# Final Copy: The Sovereign Barrier Logic
from shield_tool import ShieldTool
from shield_config import ShieldConfig

class Shield:
    def __init__(self, project_id, actuator):
        self.project_id = project_id
        self.actuator = actuator
        self.is_born = False
        
        # Initialize Triad components
        self.tool = ShieldTool(self)
        self.config = ShieldConfig()

    def trigger_birth(self):
        """Final execution of the birth sequence."""
        self.is_born = True
        self.actuator.spawn_bubble(self.project_id)
