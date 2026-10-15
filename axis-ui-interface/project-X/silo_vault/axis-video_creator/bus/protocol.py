"""Local message bus for the video_creator silos: broadcast_message(payload, channel) appends one JSON line to logs/bus.jsonl and returns a receipt.
It is a local, file-backed bus (the silos of this engine see each other's messages by reading the file). It does not send anything over the network."""
import json
import os
import time

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "bus.jsonl")


def broadcast_message(payload, channel="video_creator.bus"):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    entry = {"ts": time.time(), "channel": channel, "message": payload}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    return {"delivered": True, "channel": channel, "log": LOG}
