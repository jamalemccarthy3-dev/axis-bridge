import sys
from lib.fusion_linker_tool import FusionLinkerEngine
from config.fusion_linker_config import FusionLinkerConfig

def run_linker():
    """Main orchestrator for the Fusion Linker agent."""
    config = FusionLinkerConfig()
    engine = FusionLinkerEngine(config)
    
    try:
        if engine.sync_all_configs():
            print("Fusion Linker: System-wide configuration synchronized.")
        else:
            print("Fusion Linker: Synchronization error detected.")
    except Exception as e:
        print(f"Critical error in fusion_linker: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_linker()

