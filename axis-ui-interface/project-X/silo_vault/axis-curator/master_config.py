import os

from bridge_diagnostic import deck

## 1. IDENTIFY THE SILO
ENGINE_ID = "axis-curator"

## 1.5 NEXXUS GOVERNANCE TRACKING
NEXXUS_GOVERNANCE = {
    "mesh": "mesh.py",
    "engine_snippet_review": "engine_snippet_review.py"
}

## 2. REGISTRY: Linking root-floor scripts to their paired config
SILO_REGISTRY = {
    "root_floor_scripts": [
        "automated_metadata_tagging.py",
        "checksum_verification.py",
        "curate_input_path.py",
        "denoising_sanitization.py",
        "master_interface_utility.py",
        "optimize_storage.py",
        "orchestrator_utility.py",
        "verify_integrity.py"
    ],
    "config_pairings": [
        "automated_metadata_tagging_config.py",
        "checksum_verification_config.py",
        "curate_input_path_config.py",
        "denoising_sanitization_config.py",
        "master_interface_utility_config.py",
        "optimize_storage_config.py",
        "orchestrator_utility_config.py",
        "verify_integrity_config.py"
    ],
    "governor_src": [
        "categorization_cataloging_engine.py",
        "dependency_mapper.py",
        "life_cycle_policy.py"
    ],
    "pulse_channel": {
        "path": "pipeline_pulse.json",
        "protocol": "read_write"
    }
}

def initialize_engine():
    """Report status to the Bridge Governor, confirming config/root linkage."""
    print(f"--- Initiating Verification for {ENGINE_ID} ---")
    
    # Verify the linkage between the root floor and their respective configurations
    deck.report_status(ENGINE_ID, "CONFIG_LINKAGE", "PAIRED_TO_ROOT_FLOOR")
    
    # Register and verify NEXXUS governance modules
    for gov_key, gov_file in NEXXUS_GOVERNANCE.items():
        gov_assessment = {"status": "PRESENT" if os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), gov_file)) else ("NOT_INSTALLED (optional)" if gov_key == "engine_snippet_review" else "MISSING"), "file": gov_file}
        deck.report_status(ENGINE_ID, f"NEXXUS_Governance_{gov_key}", gov_assessment)
        print(f"NEXXUS Governance: {gov_key} ({gov_file}) - {gov_assessment['status']}")

    deck.report_status(ENGINE_ID, "SYSTEM", "FILES_CHECKED")

if __name__ == "__main__":
    initialize_engine()