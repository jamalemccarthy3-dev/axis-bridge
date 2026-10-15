"""
Configuration parameters for the drift auditor module.
Defines state drift tolerance percentages, baseline comparison frequency, and alert thresholds.
"""

DRIFT_AUDITOR_CONFIG = {
    "module_name": "drift_auditor",
    "version": "1.0.0",
    "auditor_mode": "continuous_surveillance",
    "parameters": {
        "max_allowable_drift_pct": 0.05,
        "enforce_immediate_quarantine": True,
        "audit_interval_seconds": 30,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}