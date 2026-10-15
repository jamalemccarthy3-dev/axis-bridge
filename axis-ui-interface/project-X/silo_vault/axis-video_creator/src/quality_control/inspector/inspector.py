from lib.inspector_tool import run_audit
from config.inspector_config import CONFIG

def run_inspector(target_path):
    print(f"[Quality Control] Initiating inspection on: {target_path}")
    return run_audit(target_path, CONFIG["strict_mode"], CONFIG["log_level"])
