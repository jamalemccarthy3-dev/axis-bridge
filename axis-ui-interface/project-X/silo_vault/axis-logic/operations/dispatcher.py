import json

class Dispatcher:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

    def route_request(self, task_type, payload):
        # Accessing the route_map defined in your config
        allowed = self.config.get('allowed_routes', [])
        route_map = self.config.get('route_map', {})
        
        if task_type in allowed:
            destination = route_map.get(task_type, "default_handler")
            print(f"Dispatching task '{task_type}' to '{destination}'")
            return {"status": "dispatched", "destination": destination}
        else:
            return {"status": "error", "message": "Invalid task route"}