import json
from datetime import datetime

class StatusReporter:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

    def generate_report(self, component_name, current_state):
        report = {
            "component": component_name,
            "status": current_state,
            "timestamp": datetime.utcnow().isoformat(),
            "reporting_level": self.config.get("reporting_level", "STANDARD")
        }
        return json.dumps(report, indent=4)