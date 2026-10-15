# config/loggings.py
# FORENSIC AUDIT TRAIL
LOG_CONFIG = {
    "audit_mode": "ACTIVE",
    "log_path": "../GOVERNOR/logs/forensic.log",
    "alert_on_normalization_attempt": True, # Triggers Watchdog if priority is tampered with
    "integrity_check": "SHA-256"
}
