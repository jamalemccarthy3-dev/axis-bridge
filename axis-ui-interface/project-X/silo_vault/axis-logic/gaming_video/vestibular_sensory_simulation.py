"""
Module: vestibular_sensory_simulation.py
Purpose: Final production implementation for G-force tracking, acceleration strain, 
         vision thresholds, and proportional fatigue degradation.
"""

import math
from dataclasses import dataclass
from typing import Tuple

@dataclass
class VestibularState:
    current_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    current_acceleration: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    current_g_force: float = 1.0
    vision_impairment_factor: float = 0.0
    stamina_percentage: float = 100.0
    fatigue_penalty_multiplier: float = 1.0

class VestibularSensoryEngine:
    def __init__(self, g_threshold_warning: float = 3.5, g_threshold_critical: float = 7.0):
        self.g_threshold_warning = g_threshold_warning
        self.g_threshold_critical = g_threshold_critical
        self.gravity = 9.81

    def update_simulation(self, state: VestibularState, new_velocity: Tuple[float, float, float], delta_time: float, action_intensity: float = 1.0) -> VestibularState:
        dt = delta_time
        if dt <= 0.0:
            return state

        accel_x = (new_velocity[0] - state.current_velocity[0]) / dt
        accel_y = (new_velocity[1] - state.current_velocity[1]) / dt
        accel_z = (new_velocity[2] - state.current_velocity[2]) / dt

        total_accel_magnitude = math.sqrt(accel_x**2 + accel_y**2 + (accel_z + self.gravity)**2)
        current_g = total_accel_magnitude / self.gravity
        state.current_g_force = current_g
        state.current_velocity = new_velocity
        state.current_acceleration = (accel_x, accel_y, accel_z)

        if current_g > self.g_threshold_warning:
            excess_g = current_g - self.g_threshold_warning
            range_g = self.g_threshold_critical - self.g_threshold_warning
            state.vision_impairment_factor = min(1.0, max(0.0, excess_g / range_g))
        else:
            state.vision_impairment_factor = max(0.0, state.vision_impairment_factor - (1.5 * dt))

        stamina_drain = (action_intensity * (current_g * 0.1)) * (dt * 10.0)
        state.stamina_percentage = max(0.0, state.stamina_percentage - stamina_drain)
        
        depletion_ratio = 1.0 - (state.stamina_percentage / 100.0)
        state.fatigue_penalty_multiplier = 1.0 + (depletion_ratio * 2.5)

        if action_intensity < 0.2 and state.stamina_percentage < 100.0:
            recovery = 5.0 * dt * (1.0 - depletion_ratio)
            state.stamina_percentage = min(100.0, state.stamina_percentage + recovery)

        return state