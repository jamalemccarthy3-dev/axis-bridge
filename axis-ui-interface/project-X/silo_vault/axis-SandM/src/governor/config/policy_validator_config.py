

class PolicyValidatorConfig:
    def __init__(self):
        # Operational parameters for the Policy Validator
        self.POLICY_FILE = "data/config/sovereign_shift_policy.json"
        self.STRICT_MODE = True
        
        # Thresholds for non-compliant behavior
        self.DRIFT_TOLERANCE = 0.0
        self.AUTO_REVERT = False   # drift is reported, never silently reverted