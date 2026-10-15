from lib.reporter_tool import format_and_dispatch
from config.reporter_config import CONFIG

def run_reporter(validation_results):
    print("[Quality Control] Dispatching audit report.")
    return format_and_dispatch(validation_results, CONFIG["output_format"])