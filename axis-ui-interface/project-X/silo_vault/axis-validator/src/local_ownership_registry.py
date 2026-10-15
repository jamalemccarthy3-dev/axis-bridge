"""
Core entry point for the local_ownership_registry module.
Binds configuration specs with underlying ownership registry tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.local_ownership_registry_config import LOCAL_OWNERSHIP_CONFIG
from lib.local_ownership_registry_tool import LocalOwnershipRegistryTool

class LocalOwnershipRegistry:
    def __init__(self):
        self.config = LOCAL_OWNERSHIP_CONFIG
        self.tool = LocalOwnershipRegistryTool(self.config)

    def verify(self, asset: str, owner: str, signature: bool) -> bool:
        """Executes the local ownership registry verification check."""
        owned, telemetry = self.tool.verify_asset_ownership(asset, owner, signature)
        print(f"[{self.config['module_name']}] Ownership Status -> Verified: {owned}")
        print(f"Telemetry Data: {telemetry}")
        return owned

if __name__ == "__main__":
    registry = LocalOwnershipRegistry()
    # Sanity verification mock
    registry.verify("axis_core_asset_01", "sovereign_node_alpha", True)