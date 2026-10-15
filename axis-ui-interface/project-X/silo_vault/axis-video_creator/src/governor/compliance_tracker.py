from lib.tracker_tool import log_compliance_event
from config.tracker_config import CONFIG

def track_event(event_type, module_name, status):
    """
    Records a compliance event into the secure archive.
    """
    print(f"[Governor] Logging {event_type} event for {module_name}.")
    return log_compliance_event(event_type, module_name, status, CONFIG["log_path"])
