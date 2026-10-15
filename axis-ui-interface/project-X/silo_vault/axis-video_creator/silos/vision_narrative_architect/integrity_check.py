import json
from lib.validator import validate_blueprint
from config.architect_config import CONFIG

def run_integrity_check(blueprint):
    print("[Architect] Running structural integrity check...")
    
    is_valid = validate_blueprint(blueprint, CONFIG["required_keys"])
    
    if is_valid:
        print("[Architect] Blueprint integrity verified. Ready for vault storage.")
        return True
    else:
        print("[Architect] ERROR: Blueprint integrity failed. Rejecting input.")
        return False

