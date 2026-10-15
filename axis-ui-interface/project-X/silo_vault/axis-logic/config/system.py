# config/system.py
import os

class SystemConfig:
    def __init__(self, node_name):
        self.SYSTEM_CONFIG = {
            "identity": {
                "silo_id": node_name,
                "version": "1.0.0",
                "status": "HARDENED"
            },
            "governance": {
                "governor_path": os.path.abspath("../GOVERNOR/"),
                "ledger_path": os.path.abspath("../GOVERNOR/forensics_ledger.py"),
                "audit_interval": 30
            },
            "protocols": {
                "lsp_enabled": True,
                "auto_sanitize": True,
                "max_entropy_threshold": 0.40
            },
            "operational_metrics": {
                "task_queue": [],
                "health_score": 100,
                "last_sync": "INIT_COMPLETE"
            },
            "critical_components": {
                "core_engine": "ACTIVE",
                "interface_bridge": "SECURE"
            }
        }

    def get_config(self):
        return self.SYSTEM_CONFIG

