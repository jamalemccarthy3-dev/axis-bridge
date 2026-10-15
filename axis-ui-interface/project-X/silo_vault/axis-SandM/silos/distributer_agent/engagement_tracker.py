import sys
from lib.engagement_tracker_tool import EngagementEngine
from config.engagement_tracker_config import EngagementTrackerConfig

def run_engagement_tracker():
    """Main orchestrator for the Engagement Tracker agent."""
    config = EngagementTrackerConfig()
    engine = EngagementEngine(config)
    
    try:
        metrics = engine.collect_metrics()
        print(f"Engagement tracking active. Current reach: {metrics['reach_count']}")
    except Exception as e:
        print(f"Critical error in engagement_tracker: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_engagement_tracker()
