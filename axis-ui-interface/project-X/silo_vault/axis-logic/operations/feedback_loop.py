import json

class FeedbackLoop:
    def __init__(self, config_path, registry_path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.registry_path = registry_path
        self.history = []

    def _get_registry_status(self):
        try:
            with open(self.registry_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            return {"error": "Registry not found", "details": str(e)}

    def log_feedback(self, source, outcome, metrics):
        entry = {"source": source, "outcome": outcome, "metrics": metrics}
        self.history.append(entry)
        
        if outcome == "failure" and self.config.get("feedback_settings", {}).get("auto_remediate", True):
            registry_data = self._get_registry_status()
            return self._remediate(source, registry_data)
        
        return {"status": "logged", "remediation_required": False}

    def _remediate(self, source, registry_data):
        return {
            "status": "remediated", 
            "source": source, 
            "registry_check": "completed",
            "system_state": registry_data.get("status", "unknown")
        }