"""
Module: object_dynamics_config.py
Purpose: Configuration flags, restitution constants, and sleep thresholds for the Object Dynamics module.
"""

from dataclasses import dataclass

@dataclass
class ObjectDynamicsConfig:
    SILO_ENABLED: bool = True
    DEFAULT_OBJECT_MASS: float = 2.0
    DEFAULT_RESTITUTION: float = 0.5
    SLEEP_VELOCITY_THRESHOLD: float = 0.05
    MAX_OBJECT_VELOCITY: float = 500.0

# Active global configuration instance
config = ObjectDynamicsConfig()