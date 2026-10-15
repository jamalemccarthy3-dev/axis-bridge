import requests
# Point directly to the 'config' folder
from config.ui_dashboard_config import UiDashboardConfig

class UiDashboard:
    """Engine for communicating with the remote engine to render UI data."""
    def __init__(self):
        self.config = UiDashboardConfig()

    def get_system_status(self):
        """Fetches operational data from the remote engine."""
        try:
            response = requests.get(f"{self.config.engine_api_url}/status")
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": "connection_failed"}
        except Exception as e:
            return {"error": str(e)}