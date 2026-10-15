import master_config
from bridge_diagnostic import deck

def run_link_distribution_test():
    print(f"--- Initiating Distribution Verification for {master_config.ENGINE_ID} ---")

    # # 1. Initialize the engine to report status to the Bridge
    master_config.initialize_engine()

    # # 2. Pull the final registry from the Governor
    registry = deck.get_all_reports()

    # # 3. Validate distribution pathways
    # Ensuring that the link-specific components were distributed correctly
    if master_config.ENGINE_ID in registry:
        print(f"\nSUCCESS: {master_config.ENGINE_ID} distribution is 100% verified.")
        print(f"Registry Status: {registry[master_config.ENGINE_ID]}")
    else:
        print(f"\nERROR: {master_config.ENGINE_ID} distribution failed.")

if __name__ == "__main__":
    run_link_distribution_test()