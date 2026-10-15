# ui_dashboard/ui_dashboard_config.py

class UiDashboardConfig:
    """
    Configuration for ui_dashboard.
    Points the dashboard to the remote Sovereign shift engine instance.
    """
    def __init__(self):
        self.engine_api_url = "https://engine.sovereign-shift.net/api/v1"
        self.refresh_interval = 5  # seconds
        self.dashboard_title = "Sovereign Shift Control"