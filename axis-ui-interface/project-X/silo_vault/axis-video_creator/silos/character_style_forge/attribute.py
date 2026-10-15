from lib.attribute_tool import generate_traits
from config.attribute_config import CONFIG


def run_attribute(seed=""):
    return generate_traits(CONFIG["template_id"], CONFIG["trait_count"], seed)
