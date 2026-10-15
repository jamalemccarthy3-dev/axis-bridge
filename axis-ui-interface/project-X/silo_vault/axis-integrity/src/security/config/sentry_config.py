# Sentry configuration for Access Integrity
LOG_LEVEL = "CRITICAL"
THREAT_DATABASE = "INTERNAL_SECURE"
SCAN_MODE = "REALTIME"

def get_config():
    return {
        "log_level": LOG_LEVEL,
        "db": THREAT_DATABASE,
        "mode": SCAN_MODE
    }
