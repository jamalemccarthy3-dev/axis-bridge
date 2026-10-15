"""
Module: gaming_diagnostic_test.py
Purpose: Comprehensive integration test suite verifying that all simulated subsystems,
         tool components, and configurations interact seamlessly without structural or runtime faults.
"""

import os
import sys
import unittest

# Robust path resolution to ensure local tool modules are found regardless of CWD execution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))

# the gaming modules, their tools and their configs live in gaming_video/ (modules), gaming_video/lib (tools) and gaming_video/config
for _sub in ("gaming_video", os.path.join("gaming_video", "lib"), os.path.join("gaming_video", "config")):
    _p = os.path.join(current_dir, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Import Tool Components mirroring the utility-tool-config architecture
from structural_integrity_destructibility_physics_tool import structuralintegritydestructibilityphysicstool
from spatial_persistence_object_memory_tool import SpatialPersistenceObjectMemoryTool
from object_dynamics_tool import ObjectDynamicsTool
from legendary_micro_mechanics_realism_tool import LegendaryMicroMechanicsRealismTool
from ik_procedural_foot_placement_tool import IKProceduralFootPlacementTool
from human_character_physics_tool import HumanCharacterPhysicsTool
from fauna_quadruped_dynamics_tool import FaunaQuadrupedDynamicsTool
from facial_muscle_tension_micro_simulation_tool import FacialMuscleTensionMicroSimulationTool
from environmental_dynamics_tool import EnvironmentalDynamicsTool
from deterministic_chaos_predictable_randomness_tool import DeterministicChaosPredictableRandomnessTool
from computational_constraint_solving_load_balancing_tool import ComputationalConstraintSolvingLoadBalancingTool
from ballistics_trajectory_fluid_interactions_tool import BallisticsTrajectoryFluidInteractionsTool
from angular_momentum_active_ragdoll_blending_tool import AngularMomentumActiveRagdollBlendingTool


class TestMasterSystemIntegration(unittest.TestCase):
    def setUp(self) -> None:
        """Initialize all individual module tools for cross-system testing."""
        self.dt = 0.016  # Standard 60 FPS tick delta time

        self.structural_tool = structuralintegritydestructibilityphysicstool()
        self.spatial_tool = SpatialPersistenceObjectMemoryTool()
        self.dynamics_tool = ObjectDynamicsTool()
        self.micro_mechanics_tool = LegendaryMicroMechanicsRealismTool()
        self.foot_placement_tool = IKProceduralFootPlacementTool()
        self.human_physics_tool = HumanCharacterPhysicsTool()
        self.fauna_tool = FaunaQuadrupedDynamicsTool()
        self.facial_tool = FacialMuscleTensionMicroSimulationTool()
        self.environmental_tool = EnvironmentalDynamicsTool()
        self.chaos_tool = DeterministicChaosPredictableRandomnessTool()
        self.load_balancer_tool = ComputationalConstraintSolvingLoadBalancingTool()
        self.ballistics_tool = BallisticsTrajectoryFluidInteractionsTool()
        self.ragdoll_tool = AngularMomentumActiveRagdollBlendingTool()

    def test_all_diagnostics_healthy(self) -> None:
        """Verify that every tool component successfully passes its standalone health diagnostic check."""
        tools = [
            self.structural_tool,
            self.spatial_tool,
            self.dynamics_tool,
            self.micro_mechanics_tool,
            self.foot_placement_tool,
            self.human_physics_tool,
            self.fauna_tool,
            self.facial_tool,
            self.environmental_tool,
            self.chaos_tool,
            self.load_balancer_tool,
            self.ballistics_tool,
            self.ragdoll_tool
        ]

        for tool in tools:
            diagnostic = tool.execute_diagnostic()
            self.assertEqual(diagnostic["status"], "HEALTHY", f"Tool {diagnostic.get('tool_name')} failed health diagnostic check.")

    def test_pipeline_simulation_tick(self) -> None:
        """Simulate a synchronized multi-system tick across structural, environmental, and physical domains."""
        # 1. Update Environmental conditions
        env_result = self.environmental_tool.process_tick("zone_alpha", "STORM", 15.5, self.dt)
        self.assertEqual(env_result["weather_condition"], "STORM")

        # 2. Extract wind vector for ballistic and structural processing
        wind_vector = env_result["wind_vector"]

        # 3. Process structural load under environmental stress
        struct_result = self.structural_tool.process_tick("pillar_01", applied_stress=600.0, delta_time=self.dt)
        self.assertTrue(struct_result["current_stress"] > 0.0)

        # 4. Simulate object dynamics and spatial memory
        dyn_result = self.dynamics_tool.process_tick("crate_01", external_force=(10.0, 0.0, 5.0), delta_time=self.dt)
        spatial_result = self.spatial_tool.process_tick("crate_01", position=dyn_result["position"], rotation=(0.0, 0.0, 0.0, 1.0), timestamp=100.1)
        self.assertEqual(spatial_result["object_id"], "crate_01")

        # 5. Process micro-mechanics and character physics
        micro_result = self.micro_mechanics_tool.process_tick("surface_metal_01", normal_force=250.0, slip_velocity=1.5, delta_time=self.dt)
        human_result = self.human_physics_tool.process_tick("actor_hero", applied_force=(5.0, 0.0, 2.0), delta_time=self.dt)
        fauna_result = self.fauna_tool.process_tick("wolf_alpha", target_speed=8.0, terrain_slope=10.0, delta_time=self.dt)
        facial_result = self.facial_tool.process_tick("actor_hero", target_expression_inputs={"zygomaticus": 0.8}, delta_time=self.dt)

        # 6. Run IK foot placement and determinism check
        foot_result = self.foot_placement_tool.process_tick("left_foot", target_position=(0.0, 0.1, 1.2), ground_normal=(0.0, 1.0, 0.0), step_increment=1)
        chaos_result = self.chaos_tool.process_tick("weather_noise_gen", step_increment=1)
        load_result = self.load_balancer_tool.process_tick("task_physics_sync", task_cost=150.0)

        # 7. Test ballistics and ragdoll response
        ballistics_result = self.ballistics_tool.process_tick("bullet_9mm", wind_vector=wind_vector, delta_time=self.dt)
        ragdoll_result = self.ragdoll_tool.process_tick("actor_hero", impact_torque=(0.0, 50.0, 0.0), target_blend=0.5, delta_time=self.dt)

        # Assert successful execution across the pipeline
        self.assertIn("structure_id", struct_result)
        self.assertIn("object_id", dyn_result)
        self.assertIn("assigned_task_id", load_result)
        self.assertFalse(ballistics_result["is_grounded"])
        self.assertEqual(facial_result["dominant_expression"], "SMILING")


if __name__ == "__main__":
    unittest.main()