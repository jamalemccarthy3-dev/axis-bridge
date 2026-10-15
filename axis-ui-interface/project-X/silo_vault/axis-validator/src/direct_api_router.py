"""
Core entry point for the direct_api_router module.
Binds configuration specs with underlying API router tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.direct_api_router_config import DIRECT_API_ROUTER_CONFIG
from lib.direct_api_router_tool import DirectApiRouterTool

class DirectApiRouter:
    def __init__(self):
        self.config = DIRECT_API_ROUTER_CONFIG
        self.tool = DirectApiRouterTool(self.config)

    def route(self, endpoint: str, auth: bool, secure: bool) -> bool:
        """Executes the direct API routing evaluation check."""
        approved, telemetry = self.tool.route_request(endpoint, auth, secure)
        print(f"[{self.config['module_name']}] Routing Status -> Approved: {approved}")
        print(f"Telemetry Data: {telemetry}")
        return approved

if __name__ == "__main__":
    router = DirectApiRouter()
    # Sanity verification mock
    router.route("/api/v1/axis/validate", True, True)