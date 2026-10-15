class FeedbackLooperConfig:
    def __init__(self):
        # Operational parameters for the Feedback Looper
        self.LEARNING_RATE = 0.01
        self.OPTIMIZATION_INTERVAL_HOURS = 24
        
        # Integration parameters
        self.ENABLE_AUTO_TUNING = True
        self.FEEDBACK_SOURCE_SILOS = ["distribution_agent", "content_script_writer"]

