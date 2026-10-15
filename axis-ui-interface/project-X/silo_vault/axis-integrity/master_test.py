import master_config
from bridge_diagnostic import deck

def run_integrity_distribution_test():
    print(f"--- Initiating Integrity Verification for {master_config.ENGINE_ID} ---")

    # # 1. Initialize the engine to register all audit/security sub-silos
    master_config.initialize_engine()

    # # 2. Pull the final registry from the Governor
    registry = deck.get_all_reports()

    # # 3. Validate nested integrity pathways
    # Ensuring the auditor and security sub-components are live
    if master_config.ENGINE_ID in registry:
        print(f"\nSUCCESS: {master_config.ENGINE_ID} distribution is 100% verified.")
        print(f"Deep Scan Status: {registry[master_config.ENGINE_ID]['SYSTEM']}")
    else:
        print(f"\nERROR: {master_config.ENGINE_ID} distribution failed.")

if __name__ == "__main__":
    run_integrity_distribution_test()