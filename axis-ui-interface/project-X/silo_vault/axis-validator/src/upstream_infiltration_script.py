"""
Core entry point for the upstream_infiltration_script module.
Binds configuration specs with underlying probe tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.upstream_infiltration_script_config import UPSTREAM_INFILTRATION_CONFIG
from lib.upstream_infiltration_script_tool import UpstreamInfiltrationScriptTool

class UpstreamInfiltrationScript:
    def __init__(self):
        self.config = UPSTREAM_INFILTRATION_CONFIG
        self.tool = UpstreamInfiltrationScriptTool(self.config)

    def run_probe(self, vector: str) -> bool:
        """Executes the upstream infiltration validation check."""
        success, telemetry = self.tool.execute_probe(vector)
        print(f"[{self.config['module_name']}] Probe Status -> Success: {success}")
        print(f"Telemetry Data: {telemetry}")
        return success

if __name__ == "__main__":
    script = UpstreamInfiltrationScript()
    # Sanity verification mock
    script.run_probe("axis_secure_perimeter_vector")