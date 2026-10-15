import sys
import os

# This forces Python to look in the current folder for your 'src' directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.orchestrator import Orchestrator

class UtilityBridge:
    """Simulates your Security/Utility layer."""
    def verify_access(self, access_code):
        return access_code == "SOVEREIGN_2026"

def run_master_test():
    print("--- MASTER TEST: ACCESS-LINK STARTING ---")
    
    # Initialization
    orchestrator = Orchestrator()
    bridge = UtilityBridge()
    
    # 1. Head initiates mission via Link
    mission_data = {"id": "M001", "task": "Build Engine Tools"}
    access_token = "SOVEREIGN_2026"
    
    # 2. Bridge check (The Utility Layer)
    if bridge.verify_access(access_token):
        print("[BRIDGE] Access Granted.")
        orchestrator.start_mission(mission_data)
        
        # 3. Drive Phase
        print(f"[STATE] {orchestrator.state}")
        
        # 4. Security Gatekeeper (Authorization)
        orchestrator.authorize_next_step()
        orchestrator.proceed_to_port()
        
        # 5. Port Phase
        print(f"[STATE] {orchestrator.state}")
        
        # 6. Finalize and Amnesia
        orchestrator.finalize_delivery()
        print(f"[STATE] {orchestrator.state}")
        
        if orchestrator.state == "CLEAN_AND_IDLE":
            print("--- MASTER TEST: PASSED ---")
        else:
            print("--- MASTER TEST: FAILED ---")
    else:
        print("[BRIDGE] ACCESS DENIED: Security Breach Detected.")

if __name__ == "__main__":
    run_master_test()
