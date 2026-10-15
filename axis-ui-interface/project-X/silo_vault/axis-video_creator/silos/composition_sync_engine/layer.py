from lib.layer_tool import stack_visuals
from config.layer_config import CONFIG


def run_layer(layers=None):
    """Stacks the given layers with the configured blend mode (see layer_tool.stack_visuals)."""
    return stack_visuals(CONFIG["blend_mode"], layers, CONFIG["max_layers"])
