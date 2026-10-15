"""
Module: angular_momentum_active_ragdoll_blending_config.py
Purpose: Configuration flags, torque limits, and blending rates for the Angular Momentum Active Ragdoll module.
"""

from dataclasses import dataclass

@dataclass
class RagdollConfig:
    SILO_ENABLED: bool = True
    DEFAULT_JOINT_TORQUE: float = 250.0
    DEFAULT_BLEND_SPEED: float = 5.0
    RECOVERY_TORQUE_MULTIPLIER: float = 1.5
    ANGULAR_DAMPING_FACTOR: float = 0.95

# Active global configuration instance
config = RagdollConfig()