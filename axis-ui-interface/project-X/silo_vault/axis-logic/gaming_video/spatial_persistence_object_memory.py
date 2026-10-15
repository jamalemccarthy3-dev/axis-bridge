"""
Module: spatial_persistence_object_memory.py
Purpose: Final production implementation for spatial state caching, object persistence tracking, 
         positional history logging, and memory reclamation for dynamic environment assets.
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple, List

@dataclass
class SpatialObjectRecord:
    object_id: str
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # Quaternion x, y, z, w
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    is_persistent: bool = True
    last_updated_timestamp: float = 0.0

class SpatialPersistenceEngine:
    def __init__(self, max_history_limit: int = 1000):
        self.max_history_limit = max_history_limit

    def update_object_state(self, registry: Dict[str, SpatialObjectRecord], object_id: str, position: Tuple[float, float, float], rotation: Tuple[float, float, float, float], timestamp: float) -> Dict[str, SpatialObjectRecord]:
        if object_id in registry:
            record = registry[object_id]
            record.position = position
            record.rotation = rotation
            record.last_updated_timestamp = timestamp
        else:
            if len(registry) >= self.max_history_limit:
                # Evict oldest non-persistent record if limit reached
                oldest_id = min(registry.keys(), key=lambda k: registry[k].last_updated_timestamp)
                if not registry[oldest_id].is_persistent:
                    del registry[oldest_id]
            
            registry[object_id] = SpatialObjectRecord(
                object_id=object_id,
                position=position,
                rotation=rotation,
                last_updated_timestamp=timestamp
            )

        return registry

SpatialPersistenceObjectMemory = SpatialPersistenceEngine      # alias: the name the tests and tools import
