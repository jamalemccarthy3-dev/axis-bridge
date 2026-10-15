# src/governor/governor.py
import requests
from src.governor.config.governor_utility import GovernorConfig

class Governor:
    """
    Engine for remote policy enforcement and system-wide state regulation.
    """
    def __init__(self):
        self.config = GovernorConfig()

    def enforce_policy(self, policy_name, parameters):
        """
        Dispatches policy enforcement to the remote control plane.
        """
        try:
            response = requests.post(
                f"{self.config.control_plane_url}/enforce",
                json={"policy": policy_name, "params": parameters}
            )
            return response.json() if response.status_code == 200 else {"error": "enforcement_failed"}
        except Exception as e:
            return {"error": str(e)}