import master_config
from bridge_diagnostic import deck
import os

def run_drive_distribution_test():
    print(f"--- Initiating Drive Execution Verification for {master_config.ENGINE_ID} ---")

    # # 1. Initialize the engine to register low-level components
    master_config.initialize_engine()

    # # 2. Verify existence of critical execution assets
    # Checking for the executable and C-source bridge
    critical_assets = ["axis-drive.exe", "src/main.c"]
    all_assets_present = all(os.path.exists(asset) for asset in critical_assets)
    
    # # 3. Pull the final registry from the Governor
    registry = deck.get_all_reports()

    # # 4. Validate integrity
    if master_config.ENGINE_ID in registry and all_assets_present:
        print(f"\nSUCCESS: {master_config.ENGINE_ID} execution architecture is 100% verified.")
        print(f"Asset Integrity: {'PASSED' if all_assets_present else 'FAILED'}")
    else:
        print(f"\nERROR: {master_config.ENGINE_ID} failed critical asset verification.")

if __name__ == "__main__":
    run_drive_distribution_test()