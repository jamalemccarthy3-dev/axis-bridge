from lib.builder_tool import orchestrate_silos
from config.builder_config import CONFIG


def run_master_builder(project_scope):
    """Builds one video from an order (see orchestrate_silos for the fields), through the configured stage sequence. -> the build result."""
    return orchestrate_silos(project_scope, CONFIG["priority_sequence"], CONFIG["fail_fast"])
