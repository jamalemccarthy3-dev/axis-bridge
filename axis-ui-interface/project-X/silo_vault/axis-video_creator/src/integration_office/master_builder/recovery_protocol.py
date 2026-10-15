from lib.recovery_tool import trigger_rollback
from config.recovery_config import CONFIG


def run_recovery(error_code, project_id):
    """Rolls a project back to its last stable stage (depth from the config). -> the rollback result."""
    return trigger_rollback(error_code, CONFIG["rollback_depth"], project_id)
