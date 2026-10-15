import os
import json

def initialize_system():
    # Setting the base path to the current directory where the script is located
    base_path = os.getcwd()
    print(f"Initializing system in: {base_path}")
    
    # Structure definition
    structure = {
        "requested_tools/lib": ["__init__.py", "crypto.py", "loader.py", "logger.py", "request_tools.py"],
        "silos": [
            "vision_narrative_architect/utility", "vision_narrative_architect/config",
            "storyboard_timing_precision_engine/utility", "storyboard_timing_precision_engine/config",
            "concept_vault/utility", "concept_vault/config",
            "composition_sync_engine/utility", "composition_sync_engine/config",
            "composition_final_render/utility", "composition_final_render/config",
            "character_style_forge/utility", "character_style_forge/config",
            "blueprint_compiler/utility", "blueprint_compiler/config",
            "asset_generation_library/utility", "asset_generation_library/config",
            "active_interview/utility", "active_interview/config",
            "governor/utility", "governor/config",
            "master_builder/utility", "master_builder/config",
            "inspector/utility", "inspector/config"
        ]
    }

    # Create directories
    for folder in structure["silos"]:
        os.makedirs(os.path.join(base_path, "silos", folder), exist_ok=True)
    os.makedirs(os.path.join(base_path, "requested_tools/lib"), exist_ok=True)

    # Create master_config.json
    config = {
        "system_status": "initialized",
        "root": base_path,
        "lib_path": "requested_tools/lib"
    }
    with open(os.path.join(base_path, "master_config.json"), "w") as f:
        json.dump(config, f, indent=4)

    print("System architecture successfully deployed.")

if __name__ == "__main__":
    initialize_system()

