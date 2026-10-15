"""
Module: universal_physics_foundation_config.py
Purpose: Configuration flags and constants for the Universal Physics Foundation module.
"""

from dataclasses import dataclass

@dataclass
class UniversalPhysicsConfig:
    SILO_ENABLED: bool = True
    GLOBAL_GRAVITY: float = 9.81
    DEFAULT_BODY_MASS: float = 1.0
    MAX_VELOCITY_CLAMP: float = 1000.0
    SUBSTEP_RESOLUTION: int = 4

# Active global configuration instance
config = UniversalPhysicsConfig()