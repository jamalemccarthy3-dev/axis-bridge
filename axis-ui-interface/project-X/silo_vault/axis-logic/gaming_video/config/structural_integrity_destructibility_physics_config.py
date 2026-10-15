"""
Module:
structural_integrity_destructibility_physics_config.py
Purpose: Configuration flags, load tolerances, and destruction limits for the Structural Integrity module.
"""

from dataclasses import dataclass

@dataclass
class StructuralConfig:
    SILO_ENABLED: bool = True
    DEFAULT_LOAD_CAPACITY: float = 500.0
    DESTRUCTION_THRESHOLD: float = 0.0
    STRESS_DAMAGE_MULTIPLIER: float = 20.0
    REINFORCEMENT_MAX_LIMIT: float = 1000.0

# Active global configuration instance
config = StructuralConfig()