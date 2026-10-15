import sys
import os
import requests

# Root setup: Climb up to 'axis-search_engine'
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from src.governor.config.lang_graph_config import LangGraphConfig

class LangGraphEngine:
    def __init__(self):
        self.config = LangGraphConfig()

    def run_flow(self, flow_id, initial_state):
        try:
            response = requests.post(
                f"{self.config.orchestrator_url}/execute",
                json={"flow_id": flow_id, "state": initial_state}
            )
            return response.json() if response.status_code == 200 else {"error": "flow_execution_failed"}
        except Exception as e:
            return {"error": str(e)}