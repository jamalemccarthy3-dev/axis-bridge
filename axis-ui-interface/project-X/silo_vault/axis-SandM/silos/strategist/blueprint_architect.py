import sys
from lib.blueprint_architect_tool import BlueprintArchitectEngine
from config.blueprint_architect_config import BlueprintArchitectConfig

def run_blueprint_architect():
    """Main orchestrator for the Blueprint Architect agent."""
    config = BlueprintArchitectConfig()
    engine = BlueprintArchitectEngine(config)
    
    try:
        blueprint = engine.generate_master_blueprint()
        print(f"Blueprint generation successful. Schema version: {blueprint['version']}")
    except Exception as e:
        print(f"Critical error in blueprint_architect: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_blueprint_architect()
