# Final Copy: The System Audit Logic
from audit_tool import AuditTool
from audit_config import AuditConfig

class Audit:
    def __init__(self, system_port):
        self.system_port = system_port
        self.logs = []
        
        # Initialize Triad components
        self.tool = AuditTool(self)
        self.config = AuditConfig()

    def record_event(self, event_type, project_id, details):
        """Logs all system activity into the sovereign ledger."""
        entry = f"[{event_type}] Project: {project_id} | Info: {details}"
        self.logs.append(entry)
        return True
