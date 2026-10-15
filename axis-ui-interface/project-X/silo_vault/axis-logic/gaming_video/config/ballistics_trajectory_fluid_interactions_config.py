"""
Module: ballistics_trajectory_fluid_interactions_config.py
Purpose: Configuration flags, atmospheric constants, and gravity baselines for the Ballistics Trajectory module.
"""

from dataclasses import dataclass

@dataclass
class BallisticsConfig:
    SILO_ENABLED: bool = True
    DEFAULT_AIR_DENSITY: float = 1.225
    DEFAULT_GRAVITY: float = 9.81
    STANDARD_PROJECTILE_MASS: float = 0.015
    MAX_SIMULATION_RANGE: float = 10000.0

# Active global configuration instance
config = BallisticsConfig()