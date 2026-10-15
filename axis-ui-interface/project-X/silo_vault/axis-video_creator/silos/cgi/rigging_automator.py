# operations/cgi_silo/com_lib/rigging_automator.py
from lib.rigging_automator_tool import rigging_automator_tool
from config.rigging_automator_config import rigging_automator_config

class rigging_automator:
    def __init__(self):
        self.tool = rigging_automator_tool(rigging_automator_config)

    def process_skeleton(self, mesh_data):
        """Binds skeletons to the provided mesh data."""
        return self.tool.bind_skeleton(mesh_data)

    def verify_rig(self, rig_id):
        """Verifies the integrity of the rigged asset."""
        return self.tool.validate_rig(rig_id)

if __name__ == "__main__":
    # Test block to verify initialization
    try:
        automator = rigging_automator()
        print("Rigging automator initialized successfully.")
    except Exception as e:
        print(f"Test failed with error: {e}")