# Final Copy: Sovereign Master Configuration
class Config:
    def __init__(self):
        self.settings = {
            "system_version": "2.0.0",
            "security_level": "IMPENETRABLE",
            "active_silos": "UNBOUNDED",
            "environment": "PRODUCTION",
            "global_log_level": "AUDIT_ONLY",
            # Registered Bridge
            "request_tools_path": "root/tool/request_tools.py",
            # Integrated Sandbox Configuration Module
            "sandbox_config_path": "sandbox_config.py",
            # Updated to point to the local HTML wrapper in the UI folder
            "babylon_sandbox_path": "babylon_preview.html"
        }

    def get_parameter(self, key):
        """Retrieves global system parameters for any module."""
        return self.settings.get(key, "PARAM_NOT_FOUND")

    def update_global_state(self, key, value):
        """Updates the global state; accessible by the Core Fuse mechanism."""
        self.settings[key] = value
        return True