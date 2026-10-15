"""
Configuration parameters for the compliance spec auditor module.
Defines specification validation rules, regulatory tolerance limits, and strict audit policies.
"""

COMPLIANCE_SPEC_CONFIG = {
    "module_name": "compliance_spec_auditor",
    "version": "1.0.0",
    "auditor_mode": "strict_specification_audit",
    "parameters": {
        "require_full_coverage": True,
        "enforce_zero_tolerance": True,
        "audit_timeout_seconds": 60,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}