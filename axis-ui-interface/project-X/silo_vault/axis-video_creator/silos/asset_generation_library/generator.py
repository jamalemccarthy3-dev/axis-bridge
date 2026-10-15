from lib.generator_tool import create_asset
from lib.registry_tool import register_asset
from config.generator_config import CONFIG
from config.registry_config import CONFIG as REGISTRY


def run_generator(asset_type, resolution=None, **opts):
    """Creates an asset and registers it in the manifest. -> the asset dict plus {"id", "registered": status}."""
    asset = create_asset(asset_type, resolution or CONFIG["default_resolution"], CONFIG["output_format"], **opts)
    reg = register_asset(asset, REGISTRY["db_path"])
    return dict(asset, id=reg["id"], registered=reg["status"])
