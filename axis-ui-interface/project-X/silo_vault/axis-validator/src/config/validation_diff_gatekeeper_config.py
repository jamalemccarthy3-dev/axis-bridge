"""
Configuration parameters for the validation diff gatekeeper module.
Defines zero-trust thresholds, state tolerance margins, and quarantine rules.
"""

GATEKEEPER_CONFIG = {
    "module_name": "validation_diff_gatekeeper",
    "version": "1.0.0",
    "zero_trust_mode": True,
    "strict_enforcement": True,
    "tolerance_thresholds": {
        "max_allowable_drift": 0.001,
        "hash_verification_required": True,
        "quarantine_on_failure": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}