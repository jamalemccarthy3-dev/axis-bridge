from lib.access_controler_tool import verify_permission
from config.access_controler_config import CONFIG


def run_access_check(actor_id, resource, min_clearance=None, token=None):
    """Asks the access controller whether `actor_id` may use `resource`. min_clearance defaults to the config's default level. -> its decision dict."""
    return verify_permission(actor_id, resource, min_clearance or CONFIG["default_clearance_level"], token, CONFIG)
