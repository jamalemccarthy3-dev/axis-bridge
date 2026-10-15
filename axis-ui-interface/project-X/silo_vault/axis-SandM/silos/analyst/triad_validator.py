import sys
from lib.triad_validator_tool import TriadValidatorEngine
from config.triad_validator_config import TriadValidatorConfig

def run_triad_validator():
    """Main orchestrator for the Triad Validator agent."""
    config = TriadValidatorConfig()
    engine = TriadValidatorEngine(config)
    
    try:
        # Validating the structural integrity of a target silo
        report = engine.audit_silo_structure("distributer_agent")
        print(f"Audit complete for {report['silo_name']}. Status: {report['status']}")
    except Exception as e:
        print(f"Critical error in triad_validator: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_triad_validator()
