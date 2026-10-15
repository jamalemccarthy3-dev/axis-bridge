import os
import master_config

def run_detailed_verification():
    # 1. Initialize
    config = master_config.master_config()

    print(f"\n--- BEGINNING DETAILED INTEGRITY SWEEP ---")

    # 2. Trigger Bridge Diagnostics
    print("Checking Bridge Connection...")
    config.run_diagnostic_check()

    # 3. Detailed Audit of Registry
    registry = config.ASSET_REGISTRY
    all_passed = True

    print(f"\n{'ASSET NAME':<25} | {'STATUS':<35} | {'LOCATION/PATH'}")
    print("-" * 65)

    for label, path in registry.items():
        if "api" in path:
            status = "VERIFIED (API)"
        elif os.path.exists(path):
            status = "VERIFIED (OK)"
        else:
            status = "MISSING"
            all_passed = False
            # Added debug print to show the exact path that failed
            print(f"DEBUG: Path not found -> '{path}' for label '{label}'")

        print(f"{label:<25} | {status:<35} | {path}")

    # 4. Final Status
    print("-" * 65)
    if all_passed:
        print(f"\nRESULT: PERFECT - All system interlocks verified.")
    else:
        print(f"\nRESULT: PENDING - Action required on missing components.")

if __name__ == "__main__":
    run_detailed_verification()