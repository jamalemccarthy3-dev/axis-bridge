"""
Configuration parameters for the local namespace rewriting module.
Defines namespace isolation rules, symbol collision resolution policies, and rewrite boundaries.
"""

LOCAL_NAMESPACE_CONFIG = {
    "module_name": "local_namespace_rewriting",
    "version": "1.0.0",
    "rewriting_mode": "strict_isolation",
    "parameters": {
        "prevent_global_pollution": True,
        "enforce_prefix_matching": True,
        "fallback_namespace": "axis_sovereign_local",
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}