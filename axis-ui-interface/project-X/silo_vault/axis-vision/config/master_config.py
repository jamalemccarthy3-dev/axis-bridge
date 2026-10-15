# master_config.py
import os

from bridge_diagnostic import deck

# # 1. ENGINE IDENTITY
ENGINE_ID = "AXIS VISION ENGINE"

# # 2. COMPONENTS MAPPED FROM YOUR SRC FOLDER
COMPONENTS = [
    "engine_core",
    "purge_protocol",
    "research_engine",
    "universal_port",
    "vision_logic",
    "voice_engine"
]

# # 2.5 NEXXUS GOVERNANCE TRACKING
NEXXUS_GOVERNANCE = {
    "mesh": "mesh.py",
    "engine_snippet_review": "engine_snippet_review.py"
}

# # ========================================
# # 3. HTTP BRIDGE GATEWAY CONFIG
# # ========================================
BRIDGE_CONFIG = {
    "gateway_host": "localhost",
    "gateway_port": 8000,
    "active_protocol": "http",
    "system_log_target": "system_pulse.log",
    "cors_origins": ["*"],
    "status": "integrated_with_nexxus"
}

def perform_health_assessment(component_name):
    """Deep check for C-based modules and
    configuration status."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    found = any(os.path.exists(os.path.join(root, sub, component_name + ext)) for sub in ("", "src", "lib") for ext in ("", ".c", ".h", ".py"))
    return {"status": "READY" if found else "MISSING", "wiring_integrity": "FILE_CHECK_ONLY", "capability": "NOT_RUN"}

def initialize_axis_vision():
    print(f"--- Initiating {ENGINE_ID} Verification Protocol ---")
    for component in COMPONENTS:
        assessment = perform_health_assessment(component)
        deck.report_status(ENGINE_ID, component, assessment)
        print(f"Component: {component} | Wiring: {assessment['wiring_integrity']} | Status: {assessment['status']}")
    
    # Register and verify NEXXUS governance modules
    for gov_key, gov_file in NEXXUS_GOVERNANCE.items():
        deck.report_status(ENGINE_ID, f"NEXXUS Governance [{gov_key}]", {"status": "PRESENT" if os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), gov_file)) else ("NOT_INSTALLED (optional)" if gov_key == "engine_snippet_review" else "MISSING"), "file": gov_file})
        print(f"NEXXUS Governance: {gov_key} ({gov_file})")

    deck.report_status(ENGINE_ID, "SYSTEM", "FILES_CHECKED")

if __name__ == "__main__":
    initialize_axis_vision()