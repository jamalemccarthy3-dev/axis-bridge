"""
Configuration parameters for the upstream sync diff monitor module.
Defines polling intervals, divergence alert thresholds, and sync verification parameters.
"""

UPSTREAM_SYNC_CONFIG = {
    "module_name": "upstream_sync_diff_monitor",
    "version": "1.0.0",
    "sync_mode": "continuous",
    "parameters": {
        "poll_interval_seconds": 60,
        "max_allowed_divergence_bytes": 1024,
        "auto_reconcile": False,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}