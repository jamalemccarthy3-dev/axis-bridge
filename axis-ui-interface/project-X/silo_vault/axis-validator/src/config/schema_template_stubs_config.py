"""
Configuration parameters for the schema template stubs module.
Defines template serialization formats, structural strictness rules, and stub validation parameters.
"""

SCHEMA_TEMPLATE_CONFIG = {
    "module_name": "schema_template_stubs",
    "version": "1.0.0",
    "template_mode": "strict_stub",
    "parameters": {
        "enforce_strict_types": True,
        "allow_additional_properties": False,
        "stub_fallback_enabled": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}