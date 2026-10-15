# operations/cgi_silo/com_lib/asset_registry_loader.py
from lib.asset_registry_loader_tool import asset_registry_loader_tool
from config.asset_registry_loader_config import asset_registry_loader_config

class asset_registry_loader:
    def __init__(self):
        self.tool = asset_registry_loader_tool(asset_registry_loader_config)

    def register_asset(self, asset_id, path):
        """Registers a new asset into the global registry."""
        return self.tool.add_to_registry(asset_id, path)

    def get_asset(self, asset_id):
        """Retrieves asset metadata from the registry."""
        return self.tool.fetch_asset(asset_id)

if __name__ == "__main__":
    # Test block to verify initialization
    try:
        loader = asset_registry_loader()
        print("Asset registry loader initialized successfully.")
    except Exception as e:
        print(f"Test failed with error: {e}")