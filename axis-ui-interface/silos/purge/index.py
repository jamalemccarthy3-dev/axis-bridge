# Final Copy: The Sovereign Index Directory Logic
from src.index_tool import IndexTool
from src.index_config_tool import IndexConfigTool

class Index:
    def __init__(self, system_port):
        self.system_port = system_port
        self.directory = {}
        
        # Initialize Triad components
        self.tool = IndexTool(self)
        self.config = IndexConfigTool(self)

    def update_entry(self, project_id, status_data):
        """Updates the master manifest for all projects."""
        self.directory[project_id] = status_data
        self.system_port.audit.record_event("INDEX_UPDATE", project_id, "Directory refreshed.")
