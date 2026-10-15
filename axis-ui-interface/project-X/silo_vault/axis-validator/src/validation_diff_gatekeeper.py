"""
Core entry point for the validation_diff_gatekeeper module.
Binds configuration specs with underlying tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.validation_diff_gatekeeper_config import GATEKEEPER_CONFIG
from lib.validation_diff_gatekeeper_tool import ValidationDiffGatekeeperTool

class ValidationDiffGatekeeper:
    def __init__(self):
        self.config = GATEKEEPER_CONFIG
        self.tool = ValidationDiffGatekeeperTool(self.config)

    def execute_gatekeeper_check(self, baseline: bytes, incoming: bytes) -> bool:
        """Executes the validation check across the pipeline bridge."""
        approved, telemetry = self.tool.evaluate_diff(baseline, incoming)
        print(f"[{self.config['module_name']}] Evaluation Status -> Approved: {approved}")
        print(f"Telemetry Data: {telemetry}")
        return approved

if __name__ == "__main__":
    gatekeeper = ValidationDiffGatekeeper()
    # Sanity verification mock
    gatekeeper.execute_gatekeeper_check(b"axis_baseline_state", b"axis_baseline_state")