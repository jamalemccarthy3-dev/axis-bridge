from lib.registry_tool import fetch_manifest
from config.registry_config import CONFIG

def run_registry():
    print("[Asset Library] Accessing global asset manifest.")
    return fetch_manifest(CONFIG["db_path"])
