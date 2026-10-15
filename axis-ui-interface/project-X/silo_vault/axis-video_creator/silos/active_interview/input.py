from lib.input_tool import process_raw_input
from config.input_config import CONFIG

def run_input(raw_text):
    print("[Active Interview] Processing user input stream.")
    return process_raw_input(raw_text, CONFIG["input_buffer_size"])
