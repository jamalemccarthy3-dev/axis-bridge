"""
Configuration parameters for the upstream infiltration script module.
Defines secure handshake parameters, target perimeter boundaries, and probe limitations.
"""

UPSTREAM_INFILTRATION_CONFIG = {
    "module_name": "upstream_infiltration_script",
    "version": "1.0.0",
    "operation_mode": "defensive_probe",
    "parameters": {
        "max_retry_attempts": 3,
        "timeout_seconds": 15,
        "strict_isolation": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}