"""
Module: systemic_emergency_chainreaction_config.py
Purpose: Configuration flags, cascading multipliers, and disaster threshold parameters for the Systemic Emergency module.
"""

from dataclasses import dataclass

@dataclass
class SystemicEmergencyConfig:
    SILO_ENABLED: bool = True
    DEFAULT_CASCADING_MULTIPLIER: float = 0.25
    DEFAULT_FAILURE_THRESHOLD: float = 80.0
    MAX_STRESS_LIMIT: float = 100.0
    EMERGENCY_OVERRIDE_ENABLED: bool = True

# Active global configuration instance
config = SystemicEmergencyConfig()