import psutil
import logging
from datetime import datetime
from src.governor.config.performance_monitor_config import PerformanceMonitorConfig

class PerformanceMonitorEngine:
    def __init__(self, config=None):
        self.config = config or PerformanceMonitorConfig()
        self.logger = logging.getLogger("Factory.Governor.Performance")

    def run_diagnostic(self):
        try:
            metrics = {
                "timestamp": datetime.now().isoformat(),
                "cpu_utilization": psutil.cpu_percent(interval=1),
                "memory_utilization": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage(self.config.data_path).percent
            }
            if metrics["cpu_utilization"] > self.config.cpu_limit:
                self.logger.warning(f"THRESHOLD EXCEEDED: CPU at {metrics['cpu_utilization']}%")
            return metrics
        except Exception as e:
            self.logger.critical(f"Governor diagnostic failure: {e}")
            return None