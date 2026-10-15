import sys
import time
from lib.heartbeat_monitor_tool import HeartbeatMonitorEngine
from config.heartbeat_monitor_config import HeartbeatMonitorConfig

def run_monitor():
    """Main orchestrator for the Heartbeat Monitor agent."""
    config = HeartbeatMonitorConfig()
    engine = HeartbeatMonitorEngine(config)
    
    try:
        while True:
            engine.check_silo_health()
            time.sleep(config.CHECK_INTERVAL)
    except Exception as e:
        print(f"Critical error in heartbeat_monitor: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_monitor()