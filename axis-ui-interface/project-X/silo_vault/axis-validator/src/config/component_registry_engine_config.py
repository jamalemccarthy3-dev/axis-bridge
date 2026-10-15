"""
Configuration parameters for the component registry engine module.
Defines module registration policies, strict versioning requirements, and dependency resolution rules.
"""

COMPONENT_REGISTRY_CONFIG = {
    "module_name": "component_registry_engine",
    "version": "1.0.0",
    "registry_mode": "strict_catalog",
    "parameters": {
        "require_explicit_version": True,
        "prevent_duplicate_registration": True,
        "strict_dependency_matching": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}