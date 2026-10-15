"""Master configuration for axis-video_creator. Every path is relative to the engine folder."""

MASTER_CONFIG = {
    "system_metadata": {
        "version": "1.0.0",
        "status": "hardened",
        "lib_path": "root_tools/lib",
    },
    "global_security": {
        "hash_algorithm": "SHA-256",
        "protocol_tier": "Triad_Lock",
    },
    # optional: only an engine that should act as a peer reviewer carries the review snippet
    "nexxus_governance": {
        "mesh": "mesh.py",
        "engine_snippet_review": "engine_snippet_review.py",
    },
    "silo_registry_map": {
        "vision_narrative": "silos/vision_narrative_architect",
        "storyboard_engine": "silos/storyboard_timing_precision_engine",
        "concept_vault": "silos/concept_vault",
        "sync_engine": "silos/composition_sync_engine",
        "final_render": "silos/composition_final_render",
        "style_forge": "silos/character_style_forge",
        "blueprint_compiler": "silos/blueprint_compiler",
        "asset_library": "silos/asset_generation_library",
        "active_interview": "silos/active_interview",
        "cgi": "silos/cgi",
        "governor": "src/governor",
        "master_builder": "src/integration_office/master_builder",
        "inspector": "src/quality_control/inspector",
    },
}

SILO_REGISTRY = MASTER_CONFIG["silo_registry_map"]
GOVERNANCE_OPTIONAL = ["engine_snippet_review"]
