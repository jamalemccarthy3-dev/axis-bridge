"""
Module: computational_constraint_solving_load_balancing_config.py
Purpose: Configuration flags, load balancing limits, and constraint thresholds for the Computational Load Balancing module.
"""

from dataclasses import dataclass

@dataclass
class LoadBalancingConfig:
    SILO_ENABLED: bool = True
    DEFAULT_LOAD_THRESHOLD_PERCENTAGE: float = 85.0
    DEFAULT_NODE_CAPACITY: float = 1000.0
    AUTO_THROTTLING_ENABLED: bool = True
    MAX_TASKS_PER_NODE: int = 256

# Active global configuration instance
config = LoadBalancingConfig()