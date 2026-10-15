import sys
from lib.affiliate_tracker_tool import AffiliateEngine
from config.affiliate_tracker_config import AffiliateTrackerConfig

def run_affiliate_tracker():
    """Main orchestrator for the Affiliate Tracker agent."""
    config = AffiliateTrackerConfig()
    engine = AffiliateEngine(config)
    
    try:
        report = engine.audit_referral_performance()
        print(f"Affiliate audit complete. Active partners: {report['active_partners']}")
    except Exception as e:
        print(f"Critical error in affiliate_tracker: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_affiliate_tracker()