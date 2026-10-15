from lib.assembler_tool import build_final_blueprint
from config.assembler_config import CONFIG

def run_assembler(parsed_data):
    print("[Compiler] Assembling final blueprint.")
    return build_final_blueprint(parsed_data, CONFIG["target_environment"])

