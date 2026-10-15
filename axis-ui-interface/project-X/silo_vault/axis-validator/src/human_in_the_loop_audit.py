"""
Core entry point for the human_in_the_loop_audit module.
Binds configuration specs with underlying human audit tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.human_in_the_loop_audit_config import HUMAN_AUDIT_CONFIG
from lib.human_in_the_loop_audit_tool import HumanInTheLoopAuditTool

class HumanInTheLoopAudit:
    def __init__(self):
        self.config = HUMAN_AUDIT_CONFIG
        self.tool = HumanInTheLoopAuditTool(self.config)

    def audit(self, triggered: bool, approved: bool) -> bool:
        """Executes the human-in-the-loop audit checkpoint verification."""
        status, telemetry = self.tool.evaluate_audit_checkpoint(triggered, approved)
        print(f"[{self.config['module_name']}] Audit Status -> Approved: {status}")
        print(f"Telemetry Data: {telemetry}")
        return status

if __name__ == "__main__":
    auditor = HumanInTheLoopAudit()
    # Sanity verification mock
    auditor.audit(True, True)