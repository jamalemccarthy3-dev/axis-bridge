"""
Configuration parameters for the surgical diff verifier module.
Defines patch boundary constraints, line-level tolerance rules, and verification strictness.
"""

SURGICAL_VERIFIER_CONFIG = {
    "module_name": "surgical_diff_verifier",
    "version": "1.0.0",
    "verification_mode": "strict_patch",
    "parameters": {
        "max_line_delta": 50,
        "require_explicit_context": True,
        "quarantine_unmatched_patches": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}