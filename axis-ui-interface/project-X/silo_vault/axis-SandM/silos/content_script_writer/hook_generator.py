import sys
from lib.hook_generator_tool import HookGeneratorEngine
from config.hook_generator_config import HookGeneratorConfig

def run_hook_generator():
    """Main orchestrator for the Hook Generator agent."""
    config = HookGeneratorConfig()
    engine = HookGeneratorEngine(config)
    
    try:
        hooks = engine.generate_variations("Master Narrative Concept")
        print(f"Hook generation complete. Variants created: {len(hooks)}")
    except Exception as e:
        print(f"Critical error in hook_generator: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_hook_generator()
