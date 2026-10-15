"""
Module: deterministic_chaos_predictable_randomness_config.py
Purpose: Configuration flags, seed defaults, and logistic map parameters for the Deterministic Chaos module.
"""

from dataclasses import dataclass

@dataclass
class DeterministicChaosConfig:
    SILO_ENABLED: bool = True
    DEFAULT_SEED: int = 1337
    LOGISTIC_MAP_PARAMETER: float = 3.99
    REPRODUCIBILITY_CHECK_ENABLED: bool = True
    MAX_STEP_INCREMENT: int = 100

# Active global configuration instance
config = DeterministicChaosConfig()