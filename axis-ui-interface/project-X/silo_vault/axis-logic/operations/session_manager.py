import json
import uuid

class SessionManager:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.active_sessions = {}

    def create_session(self, user_id):
        session_id = str(uuid.uuid4())
        self.active_sessions[session_id] = {
            "user_id": user_id,
            "status": "active"
        }
        return session_id

    def validate_session(self, session_id):
        return session_id in self.active_sessions