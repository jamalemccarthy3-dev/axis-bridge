# Final Copy: The Sovereign Data Scrub Logic
from src.scrub_tool import ScrubTool
from src.scrub_config import ScrubConfig

class Scrub:
    def __init__(self, system_port):
        self.system_port = system_port
        
        # Initialize Triad components
        self.tool = ScrubTool(self)
        self.config = ScrubConfig()

    def execute_scrub(self, project_id):
        """
        Performs a deep-level data scrub.
        Removes temporary cache, log artifacts, and connection residuals.
        """
        # 1. Clear interface buffer
        self.system_port.actuator.clear_cache(project_id)
        
        # 2. Scrub audit logs for specific project remnants
        self.system_port.audit.logs = [
            log for log in self.system_port.audit.logs 
            if project_id not in log
        ]
        
        return f"Silo {project_id} data scrubbed successfully."
