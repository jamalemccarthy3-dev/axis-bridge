import json
import os


class MasterConfig:
    def __init__(self):
        # System identity and status
        self.system_status = "active"
        self.self_mode = "decentralized"
        self.self_version = "2.0.0"
        # Absolute folder of this engine (axis-SandM), found from this file, never hard-coded
        self.root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Universal Library Path (relative to root_path)
        self.lib_path = "lib"

        # NEXXUS governance files this engine carries (checked by the health report, not counted as a silo)
        self.governance = {"mesh": "mesh.py", "engine_snippet_review": "engine_snippet_review.py"}
        # optional: only an engine that should act as a peer reviewer carries the review snippet
        self.governance_optional = ["engine_snippet_review"]

        # The seven silos and their utilities. "path" is relative to silos/ except the governor, which lives in src/.
        self.silos = {
            'governor': {
                "path": 'src/governor',
                "utilities": ['audit_trail_logger.py', 'deployment_gatekeeper.py', 'emergency_kill_switch.py', 'fusion_linker.py', 'heartbeat_monitor.py', 'instruction_dispacter.py', 'policy_validator.py', 'protocol_enforcer.py', 'registry_manager.py', 'resource_balancer.py', 'tool_request.py']
            },
            'analyst': {
                "path": 'analyst',
                "utilities": ['anomaly_detector.py', 'coversion_reporter.py', 'data_aggregator.py', 'feedback_looper.py', 'tool_request.py', 'triad_validator.py']
            },
            'content_script_writer': {
                "path": 'content_script_writer',
                "utilities": ['asset_compliance_check.py', 'hook_generator.py', 'multi_format_converter.py', 'narrative_engine.py', 'tone_modifier.py', 'tool_request.py']
            },
            'distributer_agent': {
                "path": 'distributer_agent',
                "utilities": ['affiliate_tracker.py', 'audience_segmenter.py', 'engagement_tracker.py', 'multi_channel_dispacter.py', 'queue_manager.py', 'tool_request.py', 'trend_harvester.py']
            },
            'strategist': {
                "path": 'strategist',
                "utilities": ['blueprint_architect.py', 'competitor_insight_scanner.py', 'resource_allocation_manager.py', 'roi_projecter.py', 'tool_request.py', 'trend_pulse_utility.py']
            },
            'technical_agent': {
                "path": 'technical_agent',
                "utilities": ['api_intergrator.py', 'deployment_pipeline.py', 'repository_auditor.py', 'system_health_monitor.py', 'tool_request.py', 'version_controller.py']
            },
            'visual_comercial_maker': {
                "path": 'visual_comercial_maker',
                "utilities": ['aesthetic_enforcer.py', 'asset_optimizer.py', 'prototype_renderer.py', 'style_sheet_synhronizer.py', 'tool_request.py', 'ui_un_component_library.py']
            }
        }

    def silo_folder(self, name):
        path = self.silos[name]["path"]
        return os.path.join(self.root_path, path if path.startswith("src") else os.path.join("silos", path))

    def get_lib_path(self):
        return os.path.join(self.root_path, self.lib_path)

    def get_config_as_json(self):
        return json.dumps({"version": self.self_version, "system_status": self.system_status, "mode": self.self_mode,
                           "silos": self.silos, "governance": self.governance}, indent=2)
