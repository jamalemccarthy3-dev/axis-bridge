

import sys
import os

# This adds the root 'axis-11m' folder to the path, 
# allowing Python to find the 'src' package.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.governor.lib.checkpoint_state_manager_tool import CheckpointStateManagerTool
from src.governor.lib.governor_alignment_utility_tool import governoralignmenttool
from src.governor.lib.performance_monitor_tool import PerformanceMonitorTool

def run_master_test():
    print("Initializing components...")
    try:
        checkpoint_manager = CheckpointStateManagerTool()
        alignment_tool = governoralignmenttool()
        perf_monitor = PerformanceMonitorTool()
        print("Governor components initialized successfully.")
    except Exception as e:
        print(f"Error during initialization: {e}")

if __name__ == "__main__":
    run_master_test()