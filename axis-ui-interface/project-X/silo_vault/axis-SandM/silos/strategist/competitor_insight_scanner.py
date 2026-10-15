import sys
from lib.competitor_insight_scanner_tool import CompetitorScannerEngine
from config.competitor_insight_scanner_config import CompetitorInsightScannerConfig

def run_competitor_scanner():
    """Main orchestrator for the Competitor Insight Scanner agent."""
    config = CompetitorInsightScannerConfig()
    engine = CompetitorScannerEngine(config)
    
    try:
        insights = engine.perform_scan()
        print(f"Competitor scan complete. Detected signals: {len(insights)}")
    except Exception as e:
        print(f"Critical error in competitor_insight_scanner: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_competitor_scanner()

