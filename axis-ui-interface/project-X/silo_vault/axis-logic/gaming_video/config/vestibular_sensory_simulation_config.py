"""
Module: vestibular_sensory_simulation_config.py
Purpose: Configuration flags, constants, and execution thresholds for the Vestibular and Sensory Simulation module.
"""

from dataclasses import dataclass

@dataclass
class VestibularConfig:
    SILO_ENABLED: bool = True
    G_THRESHOLD_WARNING: float = 3.5
    G_THRESHOLD_CRITICAL: float = 7.0
    DEFAULT_GRAVITY: float = 9.81
    STAMINA_RECOVERY_RATE: float = 5.0
    VISION_CLEAR_RATE: float = 1.5
    MAX_FATIGUE_PENALTY: float = 3.5

# Active global configuration instance
config = VestibularConfig()