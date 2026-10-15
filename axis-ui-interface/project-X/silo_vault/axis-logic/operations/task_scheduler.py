import json
import time
from datetime import datetime

class TaskScheduler:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.queue = []

    def schedule_task(self, task_name, priority, payload):
        task = {
            "name": task_name,
            "priority": priority,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.queue.append(task)
        self.queue.sort(key=lambda x: x['priority'], reverse=True)
        return True

    def get_next_task(self):
        if not self.queue:
            return None
        return self.queue.pop(0)