# Shield configuration for Access Integrity
LOG_LEVEL = "CRITICAL"
GATE_PROTOCOL = "STRICT"
AUTO_QUARANTINE = True

def get_config():
    return {
        "log_level": LOG_LEVEL,
        "protocol": GATE_PROTOCOL,
        "quarantine": AUTO_QUARANTINE
    }