import sys
from lib.asset_optimizer_tool import AssetOptimizerEngine
from config.asset_optimizer_config import AssetOptimizerConfig

def run_optimizer():
    """Main orchestrator for the Asset Optimizer agent."""
    config = AssetOptimizerConfig()
    engine = AssetOptimizerEngine(config)
    
    try:
        if engine.optimize_directory():
            print("Asset optimization: %d file(s) processed." % len(engine.report))
        else:
            print("Asset optimization did not complete: %s" % (engine.report or "no input folder or nothing to optimize"))
    except Exception as e:
        print(f"Critical error in asset_optimizer: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_optimizer()