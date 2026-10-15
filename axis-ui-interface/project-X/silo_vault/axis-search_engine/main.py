# main.py
import sys
import os

# Ensure the src directory is in the path for module imports
sys.path.append(os.path.join(os.getcwd(), "src"))

from src.governor.governor_tool import GovernorTool
from src.audit_log_utility.audit_log_utility_tool import AuditLogUtilityTool

class SystemEngine:
    """
    Main entry point for the Sovereign shift.
    Initializes the engine and monitors system status.
    """
    def __init__(self):
        self.governor = GovernorTool()
        self.logger = AuditLogUtilityTool()
        self.logger.execute("SYSTEM_INIT", "Initializing engine...")

    def run(self):
        """Standard startup sequence."""
        health = self.governor.execute("check_health")
        if health.get("status") == "nominal":
            self.logger.execute("SYSTEM_START", "Engine status nominal. Starting operations.")
            print("System Online: Sovereign shift operational.")
        else:
            self.logger.execute("SYSTEM_ERROR", "Engine failed health check.")
            print("System Alert: Startup aborted.")

if __name__ == "__main__":
    engine = SystemEngine()
    engine.run()