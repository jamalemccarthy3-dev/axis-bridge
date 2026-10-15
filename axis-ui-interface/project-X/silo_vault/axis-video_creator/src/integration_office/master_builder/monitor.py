from lib.monitor_tool import check_silo_status
from config.monitor_config import CONFIG

def run_monitor(active_silo_list):
    print("[Integration Office] Performing system health check...")
    return check_silo_status(active_silo_list, CONFIG["polling_interval"])
