"""
Module: thermal_environmental_conductivity.py
Purpose: Final production implementation for heat transfer calculations, thermal conduction, 
         environmental temperature dissipation, and material thermal capacities.
"""

from dataclasses import dataclass
from typing import Dict, Tuple

@dataclass
class ThermalNodeState:
    temperature_celsius: float = 20.0  # Ambient/current temperature
    mass: float = 1.0  # kg
    specific_heat_capacity: float = 4184.0  # J/(kg*K) - default water-like baseline
    thermal_conductivity: float = 0.6  # W/(m*K)

class ThermalEnvironmentalEngine:
    def __init__(self, ambient_temperature: float = 20.0, heat_dissipation_coefficient: float = 0.05):
        self.ambient_temperature = ambient_temperature
        self.heat_dissipation_coefficient = heat_dissipation_coefficient

    def update_thermal_node(self, node: ThermalNodeState, external_heat_input: float, delta_time: float) -> ThermalNodeState:
        dt = delta_time
        if dt <= 0.0 or node.mass <= 0.0 or node.specific_heat_capacity <= 0.0:
            return node

        # Q = m * c * delta_T -> delta_T = Q / (m * c)
        # Total heat flux: external sources minus environmental cooling/conduction gradient
        conduction_loss = self.heat_dissipation_coefficient * (node.temperature_celsius - self.ambient_temperature)
        net_heat_flow = external_heat_input - conduction_loss

        temperature_delta = (net_heat_flow * dt) / (node.mass * node.specific_heat_capacity)
        node.temperature_celsius += temperature_delta

        return node