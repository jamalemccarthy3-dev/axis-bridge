from lib.synthesizer_tool import generate_response
from config.synthesizer_config import CONFIG

def run_synthesizer(context_data):
    print("[Active Interview] Synthesizing final response output.")
    return generate_response(context_data, CONFIG["tone_profile"])
