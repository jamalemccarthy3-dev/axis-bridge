from lib.parser_tool import validate_raw_data
from config.parser_config import CONFIG

def run_parser(raw_data):
    print("[Compiler] Parsing raw structural input.")
    return validate_raw_data(raw_data, CONFIG["schema_version"])
