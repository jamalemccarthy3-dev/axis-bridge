"""
Module: systemic_emergency_chainreaction.py
Purpose: Final production implementation for cascading failure detection, systemic stress thresholds, 
         disaster propagation paths, and emergency state overrides across interconnected systems.
"""

from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class SystemNode:
    node_id: str
    stress_level: float = 0.0  # 0.0 (nominal) to 100.0 (critical failure)
    failure_threshold: float = 80.0
    is_failed: bool = False
    connected_nodes: List[str] = field(default_factory=list)

class SystemicEmergencyEngine:
    def __init__(self, cascading_multiplier: float = 0.25):
        self.cascading_multiplier = cascading_multiplier

    def apply_stress(self, nodes: Dict[str, SystemNode], target_id: str, stress_delta: float) -> Dict[str, SystemNode]:
        if target_id not in nodes or nodes[target_id].is_failed:
            return nodes

        target = nodes[target_id]
        target.stress_level = min(100.0, max(0.0, target.stress_level + stress_delta))

        # Check if the node breaches its failure threshold
        if target.stress_level >= target.failure_threshold and not target.is_failed:
            target.is_failed = True
            target.stress_level = 100.0
            
            # Cascade failure stress to adjacent/connected nodes
            spillover_stress = target.failure_threshold * self.cascading_multiplier
            for neighbor_id in target.connected_nodes:
                if neighbor_id in nodes and not nodes[neighbor_id].is_failed:
                    self.apply_stress(nodes, neighbor_id, spillover_stress)

        return nodes