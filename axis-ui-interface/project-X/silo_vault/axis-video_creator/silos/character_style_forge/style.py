from lib.style_tool import apply_aesthetic
from config.style_config import CONFIG


def run_style():
    return apply_aesthetic(CONFIG["aesthetic_preset"])
