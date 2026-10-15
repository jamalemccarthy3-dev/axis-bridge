import sys
import os

# Set the path so your modules can find each other
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from registry import Registry
from protocol import Protocol
from integrity import Integrity
from audit import Audit

class SystemEngine:
    """
    The orchestrator that initializes the Access UI Interface Module Port.
    """
    def __init__(self):
        # 1. Initialize core system services
        self.audit = Audit(self)
        self.registry = Registry(self)
        self.protocol = Protocol(self, self.registry)
        
        # 2. Status message
        self.audit.record_event("SYSTEM_START", "CORE", "Interface Module Port online.")

    def run_startup(self, project_id, silo_path):
        """
        The master boot sequence:
        Orchestrates the handshake through the Protocol pipeline.
        """
        success = self.protocol.execute_handshake(project_id, silo_path)
        if success:
            self.audit.record_event("BOOT_SUCCESS", project_id, "Project silo integrated.")
        else:
            self.audit.record_event("BOOT_FAILURE", project_id, "Handshake denied.")
        return success

    def acknowledge_registry(self, project_id):
        """Callback for the registry."""
        print(f"System Engine: Acknowledging registration for {project_id}")

# --- Engine Execution ---
if __name__ == "__main__":
    # Initialize the primary system engine
    engine = SystemEngine()

    # Configuration
    project_id = "Project_X_ID"

    # Boot sequence
    engine.run_startup(project_id, "Project X")
    engine.acknowledge_registry(project_id)

    # Local Mode: Keep the engine active without external dependencies
    print("Sovereign System Online Locally.")
    input("System waiting... (Press Enter to exit)")
































