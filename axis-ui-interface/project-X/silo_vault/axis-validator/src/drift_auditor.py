"""
Core entry point for the drift_auditor module.
Binds configuration specs with underlying drift auditor tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.drift_auditor_config import DRIFT_AUDITOR_CONFIG
from lib.drift_auditor_tool import DriftAuditorTool

class DriftAuditor:
    def __init__(self):
        self.config = DRIFT_AUDITOR_CONFIG
        self.tool = DriftAuditorTool(self.config)

    def audit(self, baseline: float, current: float) -> bool:
        """Executes the drift auditor state evaluation check."""
        stable, telemetry = self.tool.evaluate_state_drift(baseline, current)
        print(f"[{self.config['module_name']}] Audit Status -> Stable: {stable}")
        print(f"Telemetry Data: {telemetry}")
        return stable

if __name__ == "__main__":
    auditor = DriftAuditor()
    # Sanity verification mock
    auditor.audit(100.0, 101.5)