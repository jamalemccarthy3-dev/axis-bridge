"""
Core entry point for the repository_miner module.
Binds configuration specs with underlying repository miner tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.repository_miner_config import REPOSITORY_MINER_CONFIG
from lib.repository_miner_tool import RepositoryMinerTool

class RepositoryMiner:
    def __init__(self):
        self.config = REPOSITORY_MINER_CONFIG
        self.tool = RepositoryMinerTool(self.config)

    def mine(self, paths: list, depth: int) -> bool:
        """Executes the repository mining analysis check."""
        valid, telemetry = self.tool.analyze_repository_structure(paths, depth)
        print(f"[{self.config['module_name']}] Mining Status -> Valid: {valid}")
        print(f"Telemetry Data: {telemetry}")
        return valid

if __name__ == "__main__":
    miner = RepositoryMiner()
    # Sanity verification mock
    miner.mine(["src/main.py", "src/config/master_config.py"], 2)