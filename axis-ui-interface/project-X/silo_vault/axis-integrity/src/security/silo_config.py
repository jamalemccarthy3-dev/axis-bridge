# SILO_CONFIGS: The Manifest Brain
# Purpose: The single source of truth for Silo configurations.
import silo_config_tool as tool


def get_silo_manifest(silo_id):
    """-> the silo's manifest (see silo_config_tool.fetch_manifest). Its status says whether it is complete; nothing is called verified that was not."""
    return tool.fetch_manifest(silo_id)
