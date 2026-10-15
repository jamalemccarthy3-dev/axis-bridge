"""
Configuration parameters for the automated compliance license sandbox module.
Defines license verification rules, sandbox containment policies, and restriction lists.
"""

AUTOMATED_LICENSE_CONFIG = {
    "module_name": "automated_compliance_license_sandbox",
    "version": "1.0.0",
    "sandbox_mode": "strict_license_isolation",
    "parameters": {
        "require_approved_license": True,
        "isolate_on_license_violation": True,
        "audit_restricted_apis": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}