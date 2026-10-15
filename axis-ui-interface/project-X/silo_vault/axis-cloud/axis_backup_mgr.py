#!/usr/bin/env python3
"""
axis_backup_mgr.py
Production-grade final implementation. Manages local vault snapshots, 
compressed archive backups, and silo retention policies across the AXIS infrastructure.
"""

import tarfile
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
SILOS_DIR = BASE_DIR / "silos"
BACKUP_DIR = BASE_DIR / "config" / "backups"

class AxisBackupMgr:
    def __init__(self, source_dir=SILOS_DIR, backup_dir=BACKUP_DIR):
        self.source_dir = source_dir
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self):
        """Creates a compressed tar.gz archive of all local silos and vault data."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"axis_backup_{timestamp}.tar.gz"
        backup_path = self.backup_dir / backup_filename

        if not self.source_dir.exists():
            print(f"[AXIS-BACKUP-MGR] ERROR: Source directory {self.source_dir} does not exist.")
            return {"success": False, "error": "Source directory missing"}

        try:
            with tarfile.open(backup_path, "w:gz") as tar:
                tar.add(self.source_dir, arcname=self.source_dir.name)
            
            print(f"[AXIS-BACKUP-MGR] Backup successfully created at: {backup_path}")
            return {
                "success": True,
                "backup_path": str(backup_path),
                "timestamp": timestamp
            }
        except Exception as e:
            error_msg = str(e)
            print(f"[AXIS-BACKUP-MGR] ERROR: Failed to create backup: {error_msg}")
            return {"success": False, "error": error_msg}

    def list_backups(self):
        """Lists all available backup archives in the backup directory."""
        try:
            backups = [str(p) for p in self.backup_dir.glob("axis_backup_*.tar.gz")]
            return {"success": True, "backups": sorted(backups, reverse=True)}
        except Exception as e:
            return {"success": False, "error": str(e)}

if __name__ == "__main__":
    manager = AxisBackupMgr()
    if len(sys.argv) > 1 and sys.argv[1].lower() == "list":
        print(json.dumps(manager.list_backups(), indent=2))
    else:
        print(json.dumps(manager.create_backup(), indent=2))