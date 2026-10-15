# SRC/threshold.py
class ThresholdManager:
    def __init__(self, silo_name, settings):
        self.silo_name = silo_name
        self.settings = settings

    def validate(self, value):
        # Universal Logic: Shared across all four Silos
        limit = self.settings.get('threshold_value', 0.5)
        if value >= limit:
            return True, f"[{self.silo_name.upper()}] Limit {limit} reached."
        return False, "Under limit."