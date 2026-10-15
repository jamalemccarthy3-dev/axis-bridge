class EngagementTrackerConfig:
    def __init__(self):
        # Operational parameters for the Engagement Tracker
        self.TRACKING_RESOLUTION = "real-time"
        self.REPORTING_WINDOW_MIN = 60
        
        # Performance thresholds
        self.MIN_TARGET_ENGAGEMENT = 0.05
        self.ENABLE_AUTO_ALERTING = True
