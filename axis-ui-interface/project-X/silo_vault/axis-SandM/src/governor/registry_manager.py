import sys
from lib.registry_manager_tool import RegistryManagerEngine
from config.registry_manager_config import RegistryManagerConfig

def run_registry():
    """Main orchestrator for the Registry Manager agent."""
    config = RegistryManagerConfig()
    engine = RegistryManagerEngine(config)
    
    try:
        engine.sync_registry()
        print("Master Utility Registry synchronized.")
    except Exception as e:
        print(f"Critical error in registry_manager: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_registry()
