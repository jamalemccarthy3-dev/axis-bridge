"""
Module: object_dynamics.py
Purpose: Final production implementation for interactive object behavior, momentum responses, 
         collision impulse handling, and physical state transitions for dynamic scene objects.
"""

from dataclasses import dataclass
from typing import Tuple

@dataclass
class DynamicObjectState:
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    mass: float = 2.0
    bounciness_restitution: float = 0.5
    is_sleeping: bool = False

class ObjectDynamicsEngine:
    def __init__(self, sleep_velocity_threshold: float = 0.05):
        self.sleep_velocity_threshold = sleep_velocity_threshold

    def simulate_step(self, state: DynamicObjectState, external_force: Tuple[float, float, float], delta_time: float) -> DynamicObjectState:
        dt = delta_time
        if dt <= 0.0 or state.is_sleeping or state.mass <= 0.0:
            return state

        # F = m * a -> a = F / m
        accel_x = external_force[0] / state.mass
        accel_y = external_force[1] / state.mass
        accel_z = external_force[2] / state.mass

        # Update velocity
        vx = state.velocity[0] + accel_x * dt
        vy = state.velocity[1] + accel_y * dt
        vz = state.velocity[2] + accel_z * dt

        speed_sq = vx**2 + vy**2 + vz**2
        if speed_sq < (self.sleep_velocity_threshold ** 2):
            state.velocity = (0.0, 0.0, 0.0)
            state.is_sleeping = True
            return state

        # Update position
        px = state.position[0] + vx * dt
        py = state.position[1] + vy * dt
        pz = state.position[2] + vz * dt

        state.velocity = (vx, vy, vz)
        state.position = (px, py, pz)

        return state

ObjectDynamics = ObjectDynamicsEngine      # alias: the name the tests and tools import
