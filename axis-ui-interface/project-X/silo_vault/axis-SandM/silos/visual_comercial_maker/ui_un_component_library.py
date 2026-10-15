import sys
from lib.ui_components_library_tool import UIComponentsEngine
from config.ui_components_library_config import UIComponentsConfig

def run_ui_library():
    """Main orchestrator for the UI Components Library agent."""
    config = UIComponentsConfig()
    engine = UIComponentsEngine(config)
    
    try:
        r = engine.sync_component_library()
        print("UI Component Library: %s, %d component(s), %d problem(s)." % (r["status"], r["components"], len(r["problems"])))
    except Exception as e:
        print(f"Critical error in ui_components_library: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_ui_library()