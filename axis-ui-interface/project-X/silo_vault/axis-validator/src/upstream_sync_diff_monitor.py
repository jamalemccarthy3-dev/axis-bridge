"""
Core entry point for the upstream_sync_diff_monitor module.
Binds configuration parameters with underlying sync-monitoring tool execution.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.upstream_sync_diff_monitor_config import UPSTREAM_SYNC_CONFIG
from lib.upstream_sync_diff_monitor_tool import UpstreamSyncDiffMonitorTool

class UpstreamSyncDiffMonitor:
    def __init__(self):
        self.config = UPSTREAM_SYNC_CONFIG
        self.tool = UpstreamSyncDiffMonitorTool(self.config)

    def verify_sync(self, local_size: int, upstream_size: int) -> bool:
        """Executes the upstream synchronization verification check."""
        synchronized, telemetry = self.tool.analyze_sync_state(local_size, upstream_size)
        print(f"[{self.config['module_name']}] Sync Status -> Synchronized: {synchronized}")
        print(f"Telemetry Data: {telemetry}")
        return synchronized

if __name__ == "__main__":
    monitor = UpstreamSyncDiffMonitor()
    # Sanity verification mock
    monitor.verify_sync(4096, 4096)