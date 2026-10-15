import sys
from lib.aesthetics_enforcer_tool import AestheticsEnforcerEngine
from config.aesthetics_enforcer_config import AestheticsEnforcerConfig

def run_aesthetics_enforcer():
    """Main orchestrator for the Aesthetics Enforcer agent."""
    config = AestheticsEnforcerConfig()
    engine = AestheticsEnforcerEngine(config)
    
    try:
        if engine.verify_visual_integrity():
            print("Visual aesthetics verification passed.")
        else:
            print("Aesthetics check failed: %d problem(s), first: %s" % (len(engine.violations), engine.violations[:1]))
    except Exception as e:
        print(f"Critical error in aesthetics_enforcer: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_aesthetics_enforcer()