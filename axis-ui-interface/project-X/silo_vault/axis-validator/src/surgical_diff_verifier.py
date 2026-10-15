"""
Core entry point for the surgical_diff_verifier module.
Binds configuration specs with underlying surgical diff tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.surgical_diff_verifier_config import SURGICAL_VERIFIER_CONFIG
from lib.surgical_diff_verifier_tool import SurgicalDiffVerifierTool

class SurgicalDiffVerifier:
    def __init__(self):
        self.config = SURGICAL_VERIFIER_CONFIG
        self.tool = SurgicalDiffVerifierTool(self.config)

    def verify(self, lines: int, context: bool) -> bool:
        """Executes the surgical diff verification check."""
        valid, telemetry = self.tool.verify_patch(lines, context)
        print(f"[{self.config['module_name']}] Verification Status -> Valid: {valid}")
        print(f"Telemetry Data: {telemetry}")
        return valid

if __name__ == "__main__":
    verifier = SurgicalDiffVerifier()
    # Sanity verification mock
    verifier.verify(12, True)