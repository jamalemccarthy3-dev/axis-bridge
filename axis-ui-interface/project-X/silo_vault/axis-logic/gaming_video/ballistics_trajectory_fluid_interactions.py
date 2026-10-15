"""
Module: ballistics_trajectory_fluid_interactions.py
Purpose: Final production implementation for projectile ballistic trajectories, aerodynamic drag calculation, 
         fluid-structure interactions, and wind deflection modeling.
"""

from dataclasses import dataclass
from typing import Tuple

@dataclass
class BallisticProjectileState:
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    mass: float = 0.015  # kg (e.g., standard rifle round)
    drag_coefficient: float = 0.295
    cross_sectional_area: float = 0.00005  # m^2

class BallisticsTrajectoryEngine:
    def __init__(self, air_density: float = 1.225, gravity: float = 9.81):
        self.air_density = air_density
        self.gravity = gravity

    def simulate_trajectory_step(self, state: BallisticProjectileState, wind_vector: Tuple[float, float, float], delta_time: float) -> BallisticProjectileState:
        dt = delta_time
        if dt <= 0.0 or state.mass <= 0.0:
            return state

        # Relative velocity vector against wind
        rel_vx = state.velocity[0] - wind_vector[0]
        rel_vy = state.velocity[1] - wind_vector[1]
        rel_vz = state.velocity[2] - wind_vector[2]

        speed_sq = rel_vx**2 + rel_vy**2 + rel_vz**2
        speed = speed_sq ** 0.5

        # Aerodynamic Drag Force: F_d = 0.5 * rho * v^2 * Cd * A
        if speed > 0.0:
            drag_scalar = 0.5 * self.air_density * speed_sq * state.drag_coefficient * state.cross_sectional_area
            drag_ax = -(drag_scalar * (rel_vx / speed)) / state.mass
            drag_ay = -(drag_scalar * (rel_vy / speed)) / state.mass
            drag_az = -(drag_scalar * (rel_vz / speed)) / state.mass
        else:
            drag_ax, drag_ay, drag_az = 0.0, 0.0, 0.0

        # Total accelerations (including gravity on Y axis)
        accel_x = drag_ax
        accel_y = drag_ay - self.gravity
        accel_z = drag_az

        # Update velocity
        vx = state.velocity[0] + accel_x * dt
        vy = state.velocity[1] + accel_y * dt
        vz = state.velocity[2] + accel_z * dt

        # Update position
        px = state.position[0] + vx * dt
        py = max(0.0, state.position[1] + vy * dt)
        pz = state.position[2] + vz * dt

        state.velocity = (vx, vy, vz)
        state.position = (px, py, pz)

        return state

BallisticsTrajectoryFluidInteractions = BallisticsTrajectoryEngine      # alias: the name the tests and tools import
