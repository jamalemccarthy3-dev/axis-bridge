
import sys
from lib.feedback_looper_tool import FeedbackLooperEngine
from config.feedback_looper_config import FeedbackLooperConfig

def run_feedback_looper():
    """Main orchestrator for the Feedback Looper agent."""
    config = FeedbackLooperConfig()
    engine = FeedbackLooperEngine(config)
    
    try:
        # Closing the loop between performance metrics and strategy
        summary = engine.optimize_system_flow()
        print(f"System optimization cycle complete. Adjustments made: {summary['adjustments']}")
    except Exception as e:
        print(f"Critical error in feedback_looper: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_feedback_looper()