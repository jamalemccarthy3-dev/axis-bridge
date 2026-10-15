"""
Module: human_character_physics_config.py
Purpose: Configuration flags, balance thresholds, and recovery rates for the Human Character Physics module.
"""

from dataclasses import dataclass

@dataclass
class HumanPhysicsConfig:
    SILO_ENABLED: bool = True
    DEFAULT_RECOVERY_RATE: float = 5.0
    CRITICAL_BALANCE_THRESHOLD: float = 0.3
    MAX_LEAN_ANGLE_DEGREES: float = 45.0
    STABILITY_DECAY_SCALING: float = 0.01

# Active global configuration instance
config = HumanPhysicsConfig()