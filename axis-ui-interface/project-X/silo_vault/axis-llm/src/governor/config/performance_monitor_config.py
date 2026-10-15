import os

import os

class PerformanceMonitorConfig:
    def __init__(self):
        # Operational thresholds for the factory
        self.cpu_limit = 85.0
        self.memory_limit = 90.0
        self.data_path = os.getcwd()
        self.log_file = "factory_governance.log"