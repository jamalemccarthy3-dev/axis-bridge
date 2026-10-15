from lib.context_tool import update_session_state
from config.context_config import CONFIG

def run_context(current_data):
    print("[Active Interview] Updating session context.")
    return update_session_state(current_data, CONFIG["session_id"])
