#!/usr/bin/env python3
"""
axis_audit_mgr.py
Production-grade final implementation. Tracks system activity logs, 
security events, and operational audits across the AXIS infrastructure.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"
AUDIT_LOG = LOGS_DIR / "axis_audit.log"

class AxisAuditMgr:
    def __init__(self, log_file=AUDIT_LOG):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type, description, severity="INFO"):
        """Appends an immutable audit event record to the local log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "timestamp": timestamp,
            "severity": severity.upper(),
            "event_type": event_type,
            "description": description
        }

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            print(f"[AXIS-AUDIT-MGR] [{severity.upper()}] {event_type}: {description}")
            return {"success": True, "record": record}
        except Exception as e:
            error_msg = str(e)
            print(f"[AXIS-AUDIT-MGR] ERROR: Failed to write audit log: {error_msg}")
            return {"success": False, "error": error_msg}

    def read_logs(self, limit=50):
        """Retrieves the most recent audit log entries."""
        if not self.log_file.exists():
            return {"success": True, "logs": []}

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            logs = [json.loads(line.strip()) for line in lines if line.strip()]
            return {"success": True, "logs": logs[-limit:]}
        except Exception as e:
            return {"success": False, "error": str(e)}

if __name__ == "__main__":
    manager = AxisAuditMgr()
    if len(sys.argv) > 2 and sys.argv[1].lower() == "log":
        ev_type = sys.argv[2]
        desc = sys.argv[3] if len(sys.argv) > 3 else "No description provided"
        severity = sys.argv[4] if len(sys.argv) > 4 else "INFO"
        print(json.dumps(manager.log_event(ev_type, desc, severity), indent=2))
    else:
        print(json.dumps(manager.read_logs(), indent=2))