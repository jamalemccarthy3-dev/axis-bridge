"""
Configuration parameters for the scope based privilege enforcers module.
Defines role hierarchies, allowed execution scopes, and security clearance boundaries.
"""

SCOPE_PRIVILEGE_CONFIG = {
    "module_name": "scope_based_privilege_enforcers",
    "version": "1.0.0",
    "enforcement_mode": "strict_rbac",
    "parameters": {
        "default_clearance_level": "restricted",
        "require_explicit_scope": True,
        "audit_unauthorized_attempts": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}