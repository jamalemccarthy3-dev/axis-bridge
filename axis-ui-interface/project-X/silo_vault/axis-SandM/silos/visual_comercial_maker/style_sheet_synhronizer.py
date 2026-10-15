import sys
from lib.style_sheet_synchronizer_tool import StyleSheetEngine
from config.style_sheet_synchronizer_config import StyleSheetSynchronizerConfig

def run_style_sync():
    """Main orchestrator for the Style Sheet Synchronizer agent."""
    config = StyleSheetSynchronizerConfig()
    engine = StyleSheetEngine(config)
    
    try:
        if engine.sync_global_styles():
            print("Style sheets compiled from the design tokens.")
        else:
            print("Style synchronization failed: %s" % engine.last_problems)
    except Exception as e:
        print(f"Critical error in style_sheet_synchronizer: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_style_sync()
