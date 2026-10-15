class AnomalyDetectorConfig:
    def __init__(self):
        # Operational parameters for the Anomaly Detector
        self.SENSITIVITY_THRESHOLD = 0.95
        self.SCAN_INTERVAL_SECONDS = 60
        
        # Failsafe settings
        self.AUTO_LOCKDOWN_ENABLED = True
        self.ALERT_DESTINATION = "governor_silo_alert"