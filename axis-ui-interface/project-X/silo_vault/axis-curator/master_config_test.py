import master_config
from bridge_diagnostic import deck
import os

def run_curator_verification():
    print(f"--- Initiating Curator Suite Verification for {master_config.ENGINE_ID} ---")

    # 1. Initialize engine and log configurations
    master_config.initialize_engine()
    
    # 2. Cross-reference Root Floor scripts with Config Pairings
    # Ensuring every script on the floor has its corresponding config file
    mismatches = []
    for script in master_config.SILO_REGISTRY["root_floor_scripts"]:
        # Expected format: script_name (e.g. 'optimize_storage.py') -> config_name (e.g. 'optimize_storage_config.py')
        base_name = script.replace(".py", "")
        expected_config = f"{base_name}_config.py"
        
        if expected_config not in master_config.SILO_REGISTRY["config_pairings"]:
            mismatches.append(script)

    # 3. Final Integrity Report
    if not mismatches:
        print("\nSUCCESS: All root floor scripts verified with valid config pairings.")
        deck.report_status(master_config.ENGINE_ID, "INTEGRITY", "CONFIG_MATCH_PASSED")
    else:
        print(f"\nERROR: Mismatch detected in pairings: {mismatches}")
        deck.report_status(master_config.ENGINE_ID, "INTEGRITY", "CONFIG_MATCH_FAILED")

if __name__ == "__main__":
    run_curator_verification()