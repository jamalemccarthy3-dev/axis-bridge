"""
Module: legendary_micro_mechanics_realism_config.py
Purpose: Configuration flags, friction baselines, and wear limits for the Legendary Micro Mechanics module.
"""

from dataclasses import dataclass

@dataclass
class MicroMechanicsConfig:
    SILO_ENABLED: bool = True
    DEFAULT_FRICTION_COEFFICIENT: float = 0.6
    WEAR_ACCUMULATION_RATE: float = 0.001
    MAX_DEFORMATION_LIMIT: float = 5.0
    THERMAL_FRICTION_SCALING: float = 0.0001

# Active global configuration instance
config = MicroMechanicsConfig()