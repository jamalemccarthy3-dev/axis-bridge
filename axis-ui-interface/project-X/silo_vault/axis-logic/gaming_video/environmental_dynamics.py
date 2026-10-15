"""
Module: environmental_dynamics.py
Purpose: Final production implementation for ambient atmospheric changes, weather state transitions, 
         wind vector fields, and environmental condition propagation across zones.
"""

from dataclasses import dataclass
from typing import Tuple

@dataclass
class EnvironmentalState:
    temperature_celsius: float = 22.0
    humidity_percentage: float = 45.0
    wind_vector: Tuple[float, float, float] = (1.0, 0.0, 1.0)
    weather_condition: str = "CLEAR"  # CLEAR, RAIN, STORM, FOG
    ambient_light_level: float = 1.0  # 1.0 = full daylight, 0.0 = pitch black

class EnvironmentalDynamicsEngine:
    def __init__(self, transition_speed: float = 0.1):
        self.transition_speed = transition_speed

    def update_environment(self, state: EnvironmentalState, target_condition: str, target_temp: float, delta_time: float) -> EnvironmentalState:
        dt = delta_time
        if dt <= 0.0:
            return state

        state.weather_condition = target_condition
        
        # Smoothly interpolate temperature toward target
        temp_diff = target_temp - state.temperature_celsius
        state.temperature_celsius += temp_diff * (self.transition_speed * dt)

        # Adjust environmental factors based on weather condition
        if target_condition == "RAIN":
            state.humidity_percentage = min(100.0, state.humidity_percentage + (10.0 * dt))
            state.ambient_light_level = max(0.3, state.ambient_light_level - (0.2 * dt))
        elif target_condition == "STORM":
            state.humidity_percentage = 100.0
            state.ambient_light_level = max(0.1, state.ambient_light_level - (0.5 * dt))
            state.wind_vector = (state.wind_vector[0] * 2.0, state.wind_vector[1], state.wind_vector[2] * 2.0)
        else:
            state.humidity_percentage = max(20.0, state.humidity_percentage - (5.0 * dt))
            state.ambient_light_level = min(1.0, state.ambient_light_level + (0.2 * dt))

        return state

EnvironmentalDynamics = EnvironmentalDynamicsEngine      # alias: the name the tests and tools import
