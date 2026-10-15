"""
Module: environmental_dynamics_config.py
Purpose: Configuration flags, atmospheric thresholds, and transition rates for the Environmental Dynamics module.
"""

from dataclasses import dataclass

@dataclass
class EnvironmentalDynamicsConfig:
    SILO_ENABLED: bool = True
    DEFAULT_AMBIENT_TEMP: float = 22.0
    DEFAULT_HUMIDITY: float = 45.0
    TRANSITION_SPEED: float = 0.1
    MAX_WIND_VELOCITY: float = 100.0

# Active global configuration instance
config = EnvironmentalDynamicsConfig()