import sys
import time
from lib.system_health_monitor_tool import SystemHealthEngine
from config.system_health_monitor_config import SystemHealthMonitorConfig

def run_health_monitor():
    """Main orchestrator for the System Health Monitor agent."""
    config = SystemHealthMonitorConfig()
    engine = SystemHealthEngine(config)
    
    try:
        while True:
            health_report = engine.perform_diagnostic()
            if not health_report["is_stable"]:
                engine.alert_admin(health_report["error_log"])
            time.sleep(config.POLLING_INTERVAL)
    except Exception as e:
        print(f"Critical error in system_health_monitor: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_health_monitor()
