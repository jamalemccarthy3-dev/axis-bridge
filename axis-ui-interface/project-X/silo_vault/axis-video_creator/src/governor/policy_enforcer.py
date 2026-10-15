from lib.policy_tool import validate_compliance
from config.governor_config import CONFIG

def run_policy_enforcement(target_module):
    """
    Main entry point for enforcing governance.
    Evaluates a module against the active policy set.
    """
    print(f"[Governor] Initiating policy check for: {target_module}")
    return validate_compliance(target_module, CONFIG["strictness_level"], CONFIG["enforcement_protocol"])
