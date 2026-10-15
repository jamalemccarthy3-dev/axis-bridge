"""
Core entry point for the component_registry_engine module.
Binds configuration specs with underlying component registry tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.component_registry_engine_config import COMPONENT_REGISTRY_CONFIG
from lib.component_registry_engine_tool import ComponentRegistryEngineTool

class ComponentRegistryEngine:
    def __init__(self):
        self.config = COMPONENT_REGISTRY_CONFIG
        self.tool = ComponentRegistryEngineTool(self.config)

    def register(self, comp_id: str, version: str, registry: list) -> bool:
        """Executes the component registry engine validation check."""
        success, telemetry = self.tool.register_component(comp_id, version, registry)
        print(f"[{self.config['module_name']}] Registration Status -> Success: {success}")
        print(f"Telemetry Data: {telemetry}")
        return success

if __name__ == "__main__":
    engine = ComponentRegistryEngine()
    # Sanity verification mock
    engine.register("axis_validator_core", "1.0.0", [])