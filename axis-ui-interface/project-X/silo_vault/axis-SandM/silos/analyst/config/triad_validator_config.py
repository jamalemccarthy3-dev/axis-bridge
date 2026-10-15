class TriadValidatorConfig:
    def __init__(self):
        # Operational parameters for the Triad Validator
        self.REQUIRED_COMPONENTS = ["orchestrator", "tool", "config"]
        self.FAIL_ON_MISSING_FILE = True
        
        # Governance alignment
        self.LOG_AUDIT_HISTORY = True
