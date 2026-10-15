# config/utility.py

# Definitions of engine "languages" (Utility protocols)
# This keeps the core system agnostic while allowing specific communication.

ENGINE_PROTOCOLS = {
    "LOGISTICS_ENGINE": {
        "format": "BINARY_STREAM",
        "buffer_size": 1024,
        "speed": "HIGH"
    },
    "SECURITY_ENGINE": {
        "format": "ENCRYPTED_JSON",
        "buffer_size": 512,
        "speed": "SECURE"
    },
    "GAME_ENGINE": {
        "format": "UNITY_NATIVE",
        "buffer_size": 2048,
        "speed": "BURST"
    }
}

def get_protocol(engine_name):
    """Retrieves the dialect for the target engine."""
    return ENGINE_PROTOCOLS.get(engine_name, {"format": "DEFAULT", "speed": "NORMAL"})
