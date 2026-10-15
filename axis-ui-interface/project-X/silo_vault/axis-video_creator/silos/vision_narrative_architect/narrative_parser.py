import json
from lib.schema_builder import build_narrative_schema
from config.architect_config import CONFIG

def parse_input(raw_text):
    print("[Architect] Initializing narrative parse sequence.")
    structured_data = build_narrative_schema(raw_text)

    if CONFIG["STRICT_MODE"] and structured_data.get("status") != "pristine":
        raise ValueError("the narrative failed its integrity check (status %r)" % structured_data.get("status"))
    return structured_data
