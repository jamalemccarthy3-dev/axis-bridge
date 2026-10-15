import sys
import os
import requests

# Root setup
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from src.governor.config.hypothesis_engine_config import HypothesisEngineConfig

class HypothesisEngine:
    def __init__(self):
        self.config = HypothesisEngineConfig()

    def run_analysis(self, target_service, hypothesis_data):
        try:
            response = requests.post(
                f"{self.config.test_api_endpoint}/run",
                json={"service": target_service, "data": hypothesis_data}
            )
            return response.json() if response.status_code == 200 else {"error": "analysis_failed"}
        except Exception as e:
            return {"error": str(e)}