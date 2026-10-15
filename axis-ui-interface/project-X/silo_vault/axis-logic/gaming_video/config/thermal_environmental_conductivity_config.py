"""
Module: thermal_environmental_conductivity_config.py
Purpose: Configuration flags, constants, and environmental baselines for the Thermal Environmental Conductivity module.
"""

from dataclasses import dataclass

@dataclass
class ThermalConfig:
    SILO_ENABLED: bool = True
    DEFAULT_AMBIENT_TEMP_C: float = 20.0
    DEFAULT_HEAT_DISSIPATION_COEFF: float = 0.05
    MAX_TEMPERATURE_CLAMP: float = 2500.0
    MIN_TEMPERATURE_CLAMP: float = -273.15

# Active global configuration instance
config = ThermalConfig()