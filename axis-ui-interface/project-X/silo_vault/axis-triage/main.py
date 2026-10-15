import sys
import os
from grid_controller import GridController

def startup_sequence():
    """Verifies environment and ignites the GridController."""
    print("--- SYSTEM INITIALIZATION STARTING ---")
    
    # 1. Verify Master Config Exists
    if not os.path.exists('config_map.json'):
        print("[CRITICAL] config_map.json not found. Aborting.")
        sys.exit(1)
        
    print("[SYSTEM] Environment verified.")
    
    # 2. Ignite the Grid Controller
    try:
        controller = GridController()
        controller.main_loop()
    except Exception as e:
        print(f"[CRITICAL] System crash during startup: {e}")
        sys.exit(1)

if __name__ == "__main__":
    startup_sequence()