"""
Module: universal_physics_foundation.py
Purpose: Final production implementation for foundational physical laws including 
         Newtonian motion equations, kinematic solvers, and basic force vector mechanics.
"""

import math
from dataclasses import dataclass, field
from typing import Tuple

@dataclass
class PhysicsVector3D:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: 'PhysicsVector3D') -> 'PhysicsVector3D':
        return PhysicsVector3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: 'PhysicsVector3D') -> 'PhysicsVector3D':
        return PhysicsVector3D(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> 'PhysicsVector3D':
        return PhysicsVector3D(self.x * scalar, self.y * scalar, self.z * scalar)

    def magnitude(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

@dataclass
class RigidBodyState:
    position: PhysicsVector3D = field(default_factory=PhysicsVector3D)
    velocity: PhysicsVector3D = field(default_factory=PhysicsVector3D)
    acceleration: PhysicsVector3D = field(default_factory=PhysicsVector3D)
    mass: float = 1.0  # kg

class UniversalPhysicsEngine:
    def __init__(self, default_gravity: float = 9.81):
        self.default_gravity = default_gravity

    def apply_force(self, body: RigidBodyState, force: PhysicsVector3D, delta_time: float) -> RigidBodyState:
        dt = delta_time
        if dt <= 0.0 or body.mass <= 0.0:
            return body

        body.acceleration = PhysicsVector3D(
            force.x / body.mass,
            (force.y / body.mass) - self.default_gravity,
            force.z / body.mass
        )

        body.velocity = PhysicsVector3D(
            body.velocity.x + body.acceleration.x * dt,
            body.velocity.y + body.acceleration.y * dt,
            body.velocity.z + body.acceleration.z * dt
        )

        body.position = PhysicsVector3D(
            body.position.x + (body.velocity.x * dt) + (0.5 * body.acceleration.x * (dt ** 2)),
            body.position.y + (body.velocity.y * dt) + (0.5 * body.acceleration.y * (dt ** 2)),
            body.position.z + (body.velocity.z * dt) + (0.5 * body.acceleration.z * (dt ** 2))
        )

        return body