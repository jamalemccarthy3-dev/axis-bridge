"""
Configuration parameters for the drift anomaly detector module.
Defines anomaly scoring sensitivities, deviation cutoffs, and isolation flags.
"""

DRIFT_ANOMALY_CONFIG = {
    "module_name": "drift_anomaly_detector",
    "version": "1.0.0",
    "detector_mode": "statistical_outlier_detection",
    "parameters": {
        "z_score_threshold": 3.0,
        "isolation_on_anomaly": True,
        "rolling_window_size": 50,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}