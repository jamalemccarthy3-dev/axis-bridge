from lib.sync_manager_tool import get_local_nodes, verify_sync
from lib import _cfg


class SyncManager:
    def __init__(self, root=None):
        self.config = _cfg.load_config("sync_manager")
        self.grid_map = _cfg.load_grid_map()
        self.root = root

    def run_sync(self):
        """Orchestrates the synchronization check. -> the list of discrepancies (empty when the grid is in sync)."""
        local_files = get_local_nodes(self.root)
        discrepancies = verify_sync(self.grid_map, local_files)

        if not discrepancies:
            print("[SyncManager] Grid is perfectly synchronized.")
        else:
            print(f"[SyncManager] Discrepancies detected: {discrepancies}")
        return discrepancies


if __name__ == "__main__":
    SyncManager().run_sync()
