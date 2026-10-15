import unittest
import sys
import os
import json

# Adjusting path to reach the 'config' folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.master_config import MasterConfig

class TestMasterConfig(unittest.TestCase):
    def setUp(self):
        """Initialize the MasterConfig instance for testing."""
        self.config = MasterConfig()

    def test_silo_registry_completeness(self):
        """Verify all silos and their specific utilities are correctly registered."""
        expected_silos = {
            "governor": ["audit_trail_logger.py", "deployment_gatekeeper.py", "emergency_kill_switch.py", "fusion_linker.py", "heartbeat_monitor.py", "instruction_dispacter.py", "policy_validator.py", "protocol_enforcer.py", "registry_manager.py", "resource_balancer.py", "tool_request.py"],
            "analyst": ["anomaly_detector.py", "coversion_reporter.py", "data_aggregator.py", "feedback_looper.py", "tool_request.py", "triad_validator.py"],
            "content_script_writer": ["asset_compliance_check.py", "hook_generator.py", "multi_format_converter.py", "narrative_engine.py", "tone_modifier.py", "tool_request.py"],
            "distributer_agent": ["affiliate_tracker.py", "audience_segmenter.py", "engagement_tracker.py", "multi_channel_dispacter.py", "queue_manager.py", "tool_request.py", "trend_harvester.py"],
            "strategist": ["blueprint_architect.py", "competitor_insight_scanner.py", "resource_allocation_manager.py", "roi_projecter.py", "tool_request.py", "trend_pulse_utility.py"],
            "technical_agent": ["api_intergrator.py", "deployment_pipeline.py", "repository_auditor.py", "system_health_monitor.py", "tool_request.py", "version_controller.py"],
            "visual_comercial_maker": ["aesthetic_enforcer.py", "asset_optimizer.py", "prototype_renderer.py", "style_sheet_synhronizer.py", "tool_request.py", "ui_un_component_library.py"]
        }
        
        print("\n--- Starting Bridge Diagnostic ---")
        for silo, utilities in expected_silos.items():
            self.assertIn(silo, self.config.silos)
            self.assertEqual(self.config.silos[silo]["utilities"], utilities)
            print(f"Diagnostic: {silo.upper()} - ACTIVE AND READY")
        print("--- Diagnostic Complete ---\n")

    def test_lib_path_resolution(self):
        """Verify the universal library path is correctly formed."""
        lib_path = self.config.get_lib_path()
        self.assertIn("lib", lib_path)

    def test_config_json_format(self):
        """Verify the full configuration can be exported to JSON."""
        json_output = self.config.get_config_as_json()
        data = json.loads(json_output)
        self.assertEqual(data["version"], "2.0.0")
        self.assertEqual(len(data["silos"]), 7)

if __name__ == '__main__':
    unittest.main()