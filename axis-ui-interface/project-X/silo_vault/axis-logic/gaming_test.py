"""
Module: gaming_test.py
Purpose: Comprehensive integration test suite verifying that all simulated subsystems,
         core engine modules, and configurations interact seamlessly without structural or runtime faults.
"""

import os
import sys
import unittest

# Resolve and target the lib directory where the base .py modules live
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.abspath(os.path.join(current_dir, 'gaming_video'))

if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

# Import directly from the core .py module files using standard base classes
from structural_integrity_destructibility_physics import StructuralIntegrityDestructibilityPhysics
from spatial_persistence_object_memory import SpatialPersistenceObjectMemory
from object_dynamics import ObjectDynamics
from legendary_micro_mechanics_realism import LegendaryMicroMechanicsRealism
from ik_procedural_foot_placement import IKProceduralFootPlacement
from human_character_physics import HumanCharacterPhysics
from fauna_quadruped_dynamics import FaunaQuadrupedDynamics
from facial_muscle_tension_micro_simulation import FacialMuscleTensionMicroSimulation
from environmental_dynamics import EnvironmentalDynamics
from deterministic_chaos_predictable_randomness import DeterministicChaosPredictableRandomness
from computational_constraint_solving_load_balancing import ComputationalConstraintSolvingLoadBalancing
from ballistics_trajectory_fluid_interactions import BallisticsTrajectoryFluidInteractions
from angular_momentum_active_ragdoll_blending import AngularMomentumActiveRagdollBlending


class TestMasterSystemIntegration(unittest.TestCase):
    def setUp(self) -> None:
        """Initialize all individual core engine modules for cross-system testing."""
        self.dt = 0.016  # Standard 60 FPS tick delta time

        self.structural_engine = StructuralIntegrityDestructibilityPhysics()
        self.spatial_engine = SpatialPersistenceObjectMemory()
        self.dynamics_engine = ObjectDynamics()
        self.micro_mechanics_engine = LegendaryMicroMechanicsRealism()
        self.foot_placement_engine = IKProceduralFootPlacement()
        self.human_physics_engine = HumanCharacterPhysics()
        self.fauna_engine = FaunaQuadrupedDynamics()
        self.facial_engine = FacialMuscleTensionMicroSimulation()
        self.environmental_engine = EnvironmentalDynamics()
        self.chaos_engine = DeterministicChaosPredictableRandomness()
        self.load_balancer_engine = ComputationalConstraintSolvingLoadBalancing()
        self.ballistics_engine = BallisticsTrajectoryFluidInteractions()
        self.ragdoll_engine = AngularMomentumActiveRagdollBlending()

    def test_all_diagnostics_healthy(self) -> None:
        """Verify that every core module successfully passes its standalone health diagnostic check."""
        engines = [
            self.structural_engine,
            self.spatial_engine,
            self.dynamics_engine,
            self.micro_mechanics_engine,
            self.foot_placement_engine,
            self.human_physics_engine,
            self.fauna_engine,
            self.facial_engine,
            self.environmental_engine,
            self.chaos_engine,
            self.load_balancer_engine,
            self.ballistics_engine,
            self.ragdoll_engine
        ]

        for engine in engines:
            diagnostic = engine.execute_diagnostic()
            self.assertEqual(diagnostic["status"], "HEALTHY", f"Engine {diagnostic.get('module_name')} failed health diagnostic check.")

    def test_pipeline_simulation_tick(self) -> None:
        """Simulate a synchronized multi-system tick across structural, environmental, and physical domains."""
        # 1. Update Environmental conditions
        env_result = self.environmental_engine.process_tick("zone_alpha", "STORM", 15.5, self.dt)
        self.assertEqual(env_result["weather_condition"], "STORM")

        # 2. Extract wind vector for ballistic and structural processing
        wind_vector = env_result["wind_vector"]

        # 3. Process structural load under environmental stress
        struct_result = self.structural_engine.process_tick("pillar_01", applied_stress=600.0, delta_time=self.dt)
        self.assertTrue(struct_result["current_stress"] > 0.0)

        # 4. Simulate object dynamics and spatial memory
        dyn_result = self.dynamics_engine.process_tick("crate_01", external_force=(10.0, 0.0, 5.0), delta_time=self.dt)
        spatial_result = self.spatial_engine.process_tick("crate_01", position=dyn_result["position"], rotation=(0.0, 0.0, 0.0, 1.0), timestamp=100.1)
        self.assertEqual(spatial_result["object_id"], "crate_01")

        # 5. Process micro-mechanics and character physics
        micro_result = self.micro_mechanics_engine.process_tick("surface_metal_01", normal_force=250.0, slip_velocity=1.5, delta_time=self.dt)
        human_result = self.human_physics_engine.process_tick("actor_hero", applied_force=(5.0, 0.0, 2.0), delta_time=self.dt)
        fauna_result = self.fauna_engine.process_tick("wolf_alpha", target_speed=8.0, terrain_slope=10.0, delta_time=self.dt)
        facial_result = self.facial_engine.process_tick("actor_hero", target_expression_inputs={"zygomaticus": 0.8}, delta_time=self.dt)

        # 6. Run IK foot placement and determinism check
        foot_result = self.foot_placement_engine.process_tick("left_foot", target_position=(0.0, 0.1, 1.2), ground_normal=(0.0, 1.0, 0.0), step_increment=1)
        chaos_result = self.chaos_engine.process_tick("weather_noise_gen", step_increment=1)
        load_result = self.load_balancer_engine.process_tick("task_physics_sync", task_cost=150.0)

        # 7. Test ballistics and ragdoll response
        ballistics_result = self.ballistics_engine.process_tick("bullet_9mm", wind_vector=wind_vector, delta_time=self.dt)
        ragdoll_result = self.ragdoll_engine.process_tick("actor_hero", impact_torque=(0.0, 50.0, 0.0), target_blend=0.5, delta_time=self.dt)

        # Assert successful execution across the pipeline
        self.assertIn("structure_id", struct_result)
        self.assertIn("object_id", dyn_result)
        self.assertIn("assigned_task_id", load_result)
        self.assertFalse(ballistics_result["is_grounded"])
        self.assertEqual(facial_result["dominant_expression"], "SMILING")


if __name__ == "__main__":
    unittest.main()