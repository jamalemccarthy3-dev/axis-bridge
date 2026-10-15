class HeartbeatMonitorConfig:
    def __init__(self):
        # Operational parameters for the Heartbeat Monitor
        self.CHECK_INTERVAL = 30 # seconds
        self.TIMEOUT_THRESHOLD = 5 # seconds
        
        # Health state settings
        self.LOG_STATUS_CHANGES = True
        self.AUTO_RESTART_FAILED = True