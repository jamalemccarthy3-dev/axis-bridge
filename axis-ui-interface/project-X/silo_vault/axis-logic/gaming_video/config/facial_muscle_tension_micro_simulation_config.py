"""
Module: facial_muscle_tension_micro_simulation_config.py
Purpose: Configuration flags, decay coefficients, and expression thresholds for the Facial Muscle Simulation module.
"""

from dataclasses import dataclass

@dataclass
class FacialConfig:
    SILO_ENABLED: bool = True
    DEFAULT_TENSION_DECAY_RATE: float = 2.0
    EXPRESSION_THRESHOLD: float = 0.6
    MAX_TENSION_LIMIT: float = 1.0
    MICRO_TWITCH_ENABLED: bool = True

# Active global configuration instance
config = FacialConfig()