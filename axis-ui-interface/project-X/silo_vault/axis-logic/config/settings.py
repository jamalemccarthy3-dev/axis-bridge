# config/settings.py
# GLOBAL ENFORCEMENT LAYER
SETTINGS = {
    "MODE": "PRODUCTION",
    "ENCRYPTION": "AES-256",
    "AUTH_PROTOCOL": "SOVEREIGN_HANDSHAKE",
    "THROTTLE_OVERRIDE": False, # Prevents the system from resetting your 1.5 priority
    "LOG_LEVEL": "CRITICAL"
}