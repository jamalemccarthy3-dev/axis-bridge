"""
Master Configuration
(`src/config/master_config.py`) for the AXIS
Validator Suite.
Consolidates subsystem operational parameters,
security tolerances, and routing policies into a
unified manifest.
"""

AXIS_MASTER_CONFIG = {
    "system_identity": {
        "architecture": "NEXXUS_SOVEREIGN",
        "suite_name": "AXIS_VALIDATOR_SUITE",
        "version": "1.1.0",
        "execution_mode": "strict_zero_trust",
    },
    "orchestrator_parameters": {
        "enforce_zero_trust": True,
        "quarantine_on_failure": True,
        "audit_trail_active": True,
        "remote_ingestion_enabled": True,
        "default_git_branch": "main",
    },
    "subsystem_registry": {
        # NEXXUS Governance & Verification Tracking
        "nexxus_governance": {
            "mesh_module": "mesh.py",
            "snippet_reviewer": "engine_snippet_review.py",
            "enforce_active_audit": True
        },
        "validation_diff_gatekeeper": {
            "max_allowable_diff_lines": 50,
            "require_strict_patch": True,
        },
        "upstream_sync_diff_monitor": {
            "poll_interval_seconds": 60,
            "auto_quarantine_divergence": True,
        },
        "upstream_infiltration_script": {
            "block_unverified_payloads": True,
            "scan_depth_limit": 10,
        },
        "surgical_diff_verifier": {
            "precision_mode": "exact_line_match",
            "allow_fuzzy_matching": False,
        },
        "self_healing_bridge_router": {
            "max_retry_attempts": 3,
            "fallback_route_active": True,
        },
        "scope_based_privilege_enforcers": {
            "default_scope": "axis:core:read",
            "enforce_strict_containment": True,
        },
        "schema_template_stubs": {
            "require_strict_validation": True,
            "strip_unknown_fields": True,
        },
        "repository_miner": {
            "max_scan_depth": 10,
            "exclude_hidden_directories": True,
        },
        "local_ownership_registry": {
            "require_cryptographic_signature": True,
            "audit_orphan_assets": True,
        },
        "local_namespace_rewriting": {
            "prevent_global_namespace_pollution": True,
            "enforce_isolated_silos": True,
        },
        "human_in_the_loop_audit": {
            "checkpoint_timeout_seconds": 300,
            "require_explicit_signoff": True,
        },
        "extraction_parsing_pipeline": {
            "max_payload_size_mb": 10.0,
            "strict_syntax_checking": True,
        },
        "drift_auditor": {
            "max_allowable_drift_pct": 0.05,
            "audit_interval_seconds": 30,
        },
        "drift_anomaly_detector": {
            "z_score_threshold": 3.0,
            "rolling_window_size": 50,
        },
        "direct_api_router": {
            "max_requests_per_minute": 120,
            "require_auth_header": True,
            "enforce_tls_tunnel": True,
        },
        "component_registry_engine": {
            "require_explicit_version": True,
            "prevent_duplicate_registration": True,
        },
        "compliance_spec_auditor": {
            "require_full_coverage": True,
            "enforce_zero_tolerance": True,
        },
        "code_refactoring_sanitization": {
            "strip_unsafe_evals": True,
            "max_ast_mutation_depth": 15,
        },
        "autonomous_injection_daemon": {
            "max_injection_batch_size": 25,
            "require_sandbox_isolation": True,
        },
        "automated_compliance_license_sandbox": {
            "require_approved_license": True,
            "isolate_on_license_violation": True,
        },
        "remote_git_script_ingestor": {
            "request_timeout_seconds": 10,
            "ast_parsing_verification": True,
        }
    },
    "logging_policy": {
        "log_level": "INFO",
        "format": "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        "audit_trail_enabled": True,
    }
}