import json
# Assuming a central bus handler exists in root/bus
from bus.protocol import broadcast_message
from config.architect_config import CONFIG

def connect_and_broadcast(data):
    print(f"[Architect] Connecting to {CONFIG['bus_channel']}...")
    
    payload = {
        "sender": CONFIG["office_name"],
        "action": "NEW_BLUEPRINT_AVAILABLE",
        "payload": data
    }
    return broadcast_message(payload, CONFIG["bus_channel"])