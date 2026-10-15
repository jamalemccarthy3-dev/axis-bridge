"""
Core entry point for the automated_compliance_license_sandbox module.
Binds configuration specs with underlying license sandbox tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.automated_compliance_license_sandbox_config import AUTOMATED_LICENSE_CONFIG
from lib.automated_compliance_license_sandbox_tool import AutomatedComplianceLicenseSandboxTool

class AutomatedComplianceLicenseSandbox:
    def __init__(self):
        self.config = AUTOMATED_LICENSE_CONFIG
        self.tool = AutomatedComplianceLicenseSandboxTool(self.config)

    def verify(self, license_key: str, approved_list: list, sandbox: bool) -> bool:
        """Executes the automated compliance license sandbox check."""
        compliant, telemetry = self.tool.verify_license_sandbox(license_key, approved_list, sandbox)
        print(f"[{self.config['module_name']}] Compliance Status -> Compliant: {compliant}")
        print(f"Telemetry Data: {telemetry}")
        return compliant

if __name__ == "__main__":
    sandbox_module = AutomatedComplianceLicenseSandbox()
    # Sanity verification mock
    sandbox_module.verify("MIT", ["MIT", "Apache-2.0"], True)