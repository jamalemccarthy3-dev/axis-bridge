class SystemHealthMonitorConfig:
    def __init__(self):
        # Operational parameters for the System Health Monitor
        self.POLLING_INTERVAL = 10 # seconds
        self.CPU_THRESHOLD = 90.0  # percentage
        
        # Alerting settings
        self.ENABLE_AUTO_NOTIFICATIONS = True
        self.MEMORY_THRESHOLD = 90.0
        self.DISK_THRESHOLD = 95.0
        self.DISK_LATENCY_MS = 500.0
        self.LOG_PATH = "data/logs/system_health.log"
