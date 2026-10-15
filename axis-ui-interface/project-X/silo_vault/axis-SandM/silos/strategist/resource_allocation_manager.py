import sys
from lib.resource_allocation_manager_tool import ResourceAllocationEngine
from config.resource_allocation_manager_config import ResourceAllocationManagerConfig

def run_allocation_manager():
    """Main orchestrator for the Resource Allocation Manager agent."""
    config = ResourceAllocationManagerConfig()
    engine = ResourceAllocationEngine(config)
    
    try:
        report = engine.optimize_distribution()
        print(f"Resource allocation {report['status']}. Efficiency index: {report['efficiency_index']}")
    except Exception as e:
        print(f"Critical error in resource_allocation_manager: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_allocation_manager()
