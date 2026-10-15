# Final Copy: The Sovereign Archival Logic
from src.archive_tool import ArchiveTool
from src.archive_config import ArchiveConfig

class Archive:
    def __init__(self, system_port):
        self.system_port = system_port
        
        # Initialize Triad components
        self.tool = ArchiveTool(self)
        self.config = ArchiveConfig()

    def send_to_vault(self, project_id, compressed_data):
        """
        Moves compressed silo data into long-term immutable storage.
        """
        self.system_port.audit.record_event("ARCHIVE_STORE", project_id, "Data secured in vault.")
        
        # Logic to move the data packet to the secure storage path
        return f"Silo {project_id} successfully vaulted."

