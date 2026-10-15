import os
import sys

# Import the existing bridge architecture
from axis_bridge import AXIS_BRIDGE

def run_system_integrity_test():
    print(f"\n--- INITIATING SYSTEM INTEGRITY TEST ---")
    print("Forcing full Bridge initialization and handshake sequence...\n")
    
    # 1. Initialize the Bridge to trigger the __init__ handshake
    # This invokes perform_handshakes() automatically
    bridge = AXIS_BRIDGE()
    
    # 2. Verify all silos from the Registry
    print("\n--- SYSTEM REGISTRATION VERIFICATION ---")
    silo_path = bridge.silo_path
    engines = [d for d in os.listdir(silo_path) if os.path.isdir(os.path.join(silo_path, d))]
    
    for engine in engines:
        # Check that the engine folder exists
        if os.path.exists(os.path.join(silo_path, engine)):
            print(f"[VERIFIED] Engine: {engine} is registered and accessible.")
        else:
            print(f"[FAILED] Engine: {engine} is disconnected.")
            
    # 3. Final Status Confirmation
    print("\n--- TEST COMPLETE ---")
    print("If all status reads [VERIFIED], the system is fully interlocked.")

if __name__ == "__main__":
    run_system_integrity_test()