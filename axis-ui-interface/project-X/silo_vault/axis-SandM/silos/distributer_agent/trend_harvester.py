import sys
from lib.trend_harvester_tool import TrendHarvesterEngine
from config.trend_harvester_config import TrendHarvesterConfig

def run_trend_harvester():
    """Main orchestrator for the Trend Harvester agent."""
    config = TrendHarvesterConfig()
    engine = TrendHarvesterEngine(config)
    
    try:
        # Continuously monitor and report viral trend vectors
        r = engine.sync_with_market_current()
        print(f"Trend Harvester: {r['status']}, {r['signals']} signal(s), {len([t for t in r['trending'] if t['score'] >= config.MIN_VIRALITY_SCORE])} viral.")
    except Exception as e:
        print(f"Critical error in trend_harvester: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_trend_harvester()
