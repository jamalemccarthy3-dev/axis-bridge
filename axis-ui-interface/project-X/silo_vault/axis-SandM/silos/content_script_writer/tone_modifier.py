import sys
from lib.tone_modifier_tool import ToneModifierEngine
from config.tone_modifier_config import ToneModifierConfig

def run_tone_modifier():
    """Main orchestrator for the Tone Modifier agent."""
    config = ToneModifierConfig()
    engine = ToneModifierEngine(config)
    
    try:
        # Applying linguistic filters to the draft
        result = engine.adjust_narrative_voice("Input text draft...")
        print(f"Tone modification applied. Current style: {result['style']}")
    except Exception as e:
        print(f"Critical error in tone_modifier: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_tone_modifier()