# operations/cgi_silo/com_lib/scene_orchestrator.py
from lib.scene_orchestrator_tool import scene_orchestrator_tool
from config.scene_orchestrator_config import scene_orchestrator_config

class scene_orchestrator:
    def __init__(self):
        self.tool = scene_orchestrator_tool(scene_orchestrator_config)

    def build_scene(self, storyboard_data):
        """Processes storyboard data into the scene graph."""
        return self.tool.construct_scene(storyboard_data)

    def update_node(self, node_id, parameters):
        """Updates specific elements within the current scene."""
        return self.tool.modify_node(node_id, parameters)

if __name__ == "__main__":
    # Test block to verify initialization
    try:
        orchestrator = scene_orchestrator()
        print("Scene orchestrator initialized successfully.")
    except Exception as e:
        print(f"Test failed with error: {e}")