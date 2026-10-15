"""
Configuration parameters for the local ownership registry module.
Defines asset ownership validation rules, cryptographic verification requirements, and registry scopes.
"""

LOCAL_OWNERSHIP_CONFIG = {
    "module_name": "local_ownership_registry",
    "version": "1.0.0",
    "registry_mode": "strict_sovereign",
    "parameters": {
        "require_cryptographic_signature": True,
        "allow_unclaimed_assets": False,
        "registry_lockdown_enabled": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}