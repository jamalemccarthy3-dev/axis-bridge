"""
Core entry point for the autonomous_injection_daemon module.
Binds configuration specs with underlying autonomous injection tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.autonomous_ingestion_daemon_config import AUTONOMOUS_INJECTION_CONFIG
from lib.autonomous_ingestion_daemon_tool import AutonomousInjectionDaemonTool

class AutonomousInjectionDaemon:
    def __init__(self):
        self.config = AUTONOMOUS_INJECTION_CONFIG
        self.tool = AutonomousInjectionDaemonTool(self.config)

    def inject(self, batch_size: int, sandbox: bool) -> bool:
        """Executes the autonomous injection daemon verification check."""
        success, telemetry = self.tool.execute_injection(batch_size, sandbox)
        print(f"[{self.config['module_name']}] Injection Status -> Success: {success}")
        print(f"Telemetry Data: {telemetry}")
        return success

if __name__ == "__main__":
    daemon = AutonomousInjectionDaemon()
    # Sanity verification mock
    daemon.inject(10, True)