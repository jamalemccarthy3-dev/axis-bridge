import master_config
from bridge_diagnostic import deck

def run_standard_verification():
    print(f"--- Initiating Verification for {master_config.ENGINE_ID} ---")

    # # 1. Initialize the engine to report status to the Bridge
    master_config.initialize_engine()

    # # 2. Pull the final registry from the Governor
    registry = deck.get_all_reports()

    # # 3. Final verification check
    if master_config.ENGINE_ID in registry:
        print(f"\nSUCCESS: {master_config.ENGINE_ID} is 100% verified and wired.")
    else:
        print(f"\nERROR: {master_config.ENGINE_ID} failed verification.")

if __name__ == "__main__":
    run_standard_verification()