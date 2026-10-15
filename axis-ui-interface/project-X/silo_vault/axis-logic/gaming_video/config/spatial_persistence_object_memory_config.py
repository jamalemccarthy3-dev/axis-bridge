"""
Module: spatial_persistence_object_memory_config.py
Purpose: Configuration flags, cache limits, and memory parameters for the Spatial Persistence Object Memory module.
"""

from dataclasses import dataclass

@dataclass
class SpatialMemoryConfig:
    SILO_ENABLED: bool = True
    MAX_HISTORY_LIMIT: int = 1000
    AUTO_RECLAMATION_ENABLED: bool = True
    CACHE_EXPIRATION_SECONDS: float = 300.0
    DEFAULT_PERSISTENCE_STATE: bool = True

# Active global configuration instance
config = SpatialMemoryConfig()