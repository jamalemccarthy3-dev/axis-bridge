from lib.regulator_tool import verify_regulatory_alignment
from config.regulator_config import CONFIG

def run_regulation_check(payload):
    """
    Final gatekeeper check before payload execution.
    Verifies that the operation adheres to sovereign jurisdiction rules.
    """
    print("[Governor] Running final regulatory alignment check...")
    return verify_regulatory_alignment(payload, CONFIG["jurisdiction_rules"])
