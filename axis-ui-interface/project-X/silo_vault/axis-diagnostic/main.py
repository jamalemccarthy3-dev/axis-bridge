# main.py
from src.lib.dna_scanner_utility_tool import dnascannertool
from src.lib.bridge_orchestration_utility_tool import bridgeorchestrationtool
from src.lib.audit_integrity_utility_tool import auditintegrityutilitytool

from src.governor.lib.governor_sync_utility_tool import governorsynctool
from src.governor.lib.governor_pulse_utility_tool import governorpulsetool
from src.governor.lib.governor_override_utility_tool import governoroverridetool
from src.governor.lib.governor_flow_control_utility_tool import governorflowcontroltool
from src.governor.lib.governor_handshake_utility_tool import governorhandshaketool

class DiagnosticEngine:
    def __init__(self):
        # initialize governor cluster
        self.gov_sync = governorsynctool()
        self.gov_pulse = governorpulsetool()
        self.gov_override = governoroverridetool()
        self.gov_flow = governorflowcontroltool()
        self.gov_handshake = governorhandshaketool()
        
        # initialize core utilities
        self.scanner = dnascannertool()
        self.bridge = bridgeorchestrationtool()
        self.audit = auditintegrityutilitytool()
        
        print("diagnosticengine: core and governor modules initialized.")

if __name__ == "__main__":
    engine = diagnosticengine()