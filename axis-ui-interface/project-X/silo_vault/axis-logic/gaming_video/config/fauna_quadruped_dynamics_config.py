"""
Module: fauna_quadruped_dynamics_config.py
Purpose: Configuration flags, gait thresholds, and speed limits for the Fauna Quadruped Dynamics module.
"""

from dataclasses import dataclass

@dataclass
class FaunaConfig:
    SILO_ENABLED: bool = True
    MAX_QUADRUPED_SPEED: float = 15.0
    WALK_SPEED_THRESHOLD: float = 2.0
    TROT_SPEED_THRESHOLD: float = 7.0
    MAX_PITCH_ANGLE: float = 30.0

# Active global configuration instance
config = FaunaConfig()