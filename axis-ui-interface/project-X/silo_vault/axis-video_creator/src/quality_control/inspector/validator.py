from lib.validator_tool import evaluate_against_protocol
from config.validator_config import CONFIG

def run_validator(inspection_data):
    print("[Quality Control] Validating data against established protocols...")
    return evaluate_against_protocol(inspection_data, CONFIG["threshold_level"])
