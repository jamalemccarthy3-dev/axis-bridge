import sys
from lib.policy_validator_tool import PolicyValidatorEngine
from config.policy_validator_config import PolicyValidatorConfig

def run_validator():
    """Main orchestrator for the Policy Validator agent."""
    config = PolicyValidatorConfig()
    engine = PolicyValidatorEngine(config)
    
    try:
        if engine.verify_system_policies():
            print("System policy verification passed.")
        else:
            print("Policy drift detected. Reverting to baseline.")
    except Exception as e:
        print(f"Critical error in policy_validator: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_validator()