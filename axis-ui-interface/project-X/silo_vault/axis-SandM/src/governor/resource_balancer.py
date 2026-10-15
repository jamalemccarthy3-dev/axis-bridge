import sys
import os
from lib.resource_balancer_tool import ResourceBalancerEngine
from config.resource_balancer_config import ResourceBalancerConfig

def run_balancer():
    """Main orchestrator for the Resource Balancer agent."""
    config = ResourceBalancerConfig()
    engine = ResourceBalancerEngine(config)
    
    try:
        status = engine.execute_balancing()
        if status:
            print("Resource allocation balanced successfully.")
        else:
            print("Balancing failed: Threshold violation detected.")
    except Exception as e:
        print(f"Critical error in resource_balancer: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_balancer()