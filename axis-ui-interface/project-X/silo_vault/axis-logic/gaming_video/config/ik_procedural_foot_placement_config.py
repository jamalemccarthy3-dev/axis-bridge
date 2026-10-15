"""
Module: ik_procedural_foot_placement_config.py
Purpose: Configuration flags, leg length parameters, and smoothing rates for the IK Procedural Foot Placement module.
"""

from dataclasses import dataclass

@dataclass
class FootPlacementConfig:
    SILO_ENABLED: bool = True
    DEFAULT_LEG_LENGTH: float = 1.0
    SMOOTHING_SPEED: float = 15.0
    MAX_STEP_HEIGHT: float = 0.5
    GROUND_OFFSET_TOLERANCE: float = 0.02

# Active global configuration instance
config = FootPlacementConfig()