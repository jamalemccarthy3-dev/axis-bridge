import sys
from lib.protocol_enforcer_tool import ProtocolEnforcerEngine
from config.protocol_enforcer_config import ProtocolEnforcerConfig

def run_enforcer():
    """Main orchestrator for the Protocol Enforcer agent."""
    config = ProtocolEnforcerConfig()
    engine = ProtocolEnforcerEngine(config)
    
    try:
        if engine.validate_active_protocols():
            print("All protocols validated successfully.")
        else:
            print("Protocol breach detected. Initiating lockdown.")
    except Exception as e:
        print(f"Critical error in protocol_enforcer: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_enforcer()
