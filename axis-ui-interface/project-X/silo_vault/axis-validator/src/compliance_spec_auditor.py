"""
Core entry point for the compliance_spec_auditor module.
Binds configuration specs with underlying compliance auditor tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.compliance_spec_auditor_config import COMPLIANCE_SPEC_CONFIG
from lib.compliance_spec_auditor_tool import ComplianceSpecAuditorTool

class ComplianceSpecAuditor:
    def __init__(self):
        self.config = COMPLIANCE_SPEC_CONFIG
        self.tool = ComplianceSpecAuditorTool(self.config)

    def audit(self, implemented: list, required: list) -> bool:
        """Executes the compliance specification audit check."""
        compliant, telemetry = self.tool.audit_specification(implemented, required)
        print(f"[{self.config['module_name']}] Audit Status -> Compliant: {compliant}")
        print(f"Telemetry Data: {telemetry}")
        return compliant

if __name__ == "__main__":
    auditor = ComplianceSpecAuditor()
    # Sanity verification mock
    auditor.audit(["zero_trust", "modular_silos", "audit_logging"], ["zero_trust", "modular_silos", "audit_logging"])