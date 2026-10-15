import sys
from lib.narrative_engine_tool import NarrativeEngine
from config.narrative_engine_config import NarrativeEngineConfig

def run_narrative_engine():
    """Main orchestrator for the Narrative Engine agent."""
    config = NarrativeEngineConfig()
    engine = NarrativeEngine(config)
    
    try:
        story = engine.generate_structure("Draft concept...")
        print(f"Narrative structure built. Arc type: {story['arc_type']}")
    except Exception as e:
        print(f"Critical error in narrative_engine: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_narrative_engine()
