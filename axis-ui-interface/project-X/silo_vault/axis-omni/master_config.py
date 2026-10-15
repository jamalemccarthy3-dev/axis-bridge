import os

from bridge_diagnostic import deck

HERE = os.path.dirname(os.path.abspath(__file__))

# ## 1. IDENTIFY THE SILO
ENGINE_ID = "axis-omni"

# 1.5 NEXXUS GOVERNANCE TRACKING
NEXXUS_GOVERNANCE = {
    "mesh": "mesh.py",
    "engine_snippet_review": "engine_snippet_review.py"
}

# ## 2. DEFINE THE REGISTRY MAP
SILO_REGISTRY = {
    ".": [
        "omni_protocol.py",
        "test_protocol.py",
        "voice.py",
        "test_voice.py"
    ],
    "bank": [
        "__init__.py"
    ],
    "bank/performance_modes": [
        "__init__.py",
        "american_english.json",
        "british.json",
        "celebrate.json",
        "corporate.json",
        "country.json",
        "narrative_warm.json",
        "poetry.json",
        "rap.json",
        "spanish.json",
        "spoken_word.json",
        "standard_neutral.json",
        "theatrical.json",
        "british.txt"
    ],
    "bank/templates": [
        "__init__.py",
        "commercial.txt",
        "conversation.txt",
        "psa.txt",
        "quotes.txt",
        "surprises.txt"
    ],
    "lib": [
        "__init__.py",
        "aggregator.c",
        "aggregator.h",
        "common_utils.c",
        "common_utils.h",
        "fetcher.c",
        "fetcher.h",
        "generator.c",
        "generator.h",
        "logger.c",
        "logger.h",
        "metronome.c",
        "metronome.h",
        "omni_protocol.cpp",
        "omni_protocol.h",
        "pace_controller.c",
        "pace_controller.h",
        "pipe.c",
        "pipe.h",
        "post.c",
        "post.h",
        "shunt.c",
        "shunt.h",
        "speech_engine.c",
        "speech_engine.h",
        "synthesizer.c",
        "synthesizer.h",
        "system_registry.h",
        "vibe_profiles.c",
        "vibe_profiles.h"
    ],
    "src": [
        "__init__.py",
        "input_handler.c",
        "input_handler.h",
        "main.c"
    ],
    "links": ["__init__.py", "AXIS_LLM_link.py"],
    "access": ["__init__.py", "access_omni_path.py"],
}

# Components that are listed here but have no files yet are reported as PLANNED, never as ready. None right now: links/ and access/ exist and are in SILO_REGISTRY.
PLANNED = {}


def perform_health_assessment(component_name):
    """A real check: every file the registry lists must exist, and a code or data file must not be empty.
    READY only when all of them pass; otherwise the status says what is wrong."""
    files = SILO_REGISTRY.get(component_name, [])
    missing = [f for f in files if not os.path.isfile(os.path.join(HERE, component_name, f))]
    empty = [f for f in files if f not in missing and f != "__init__.py" and os.path.getsize(os.path.join(HERE, component_name, f)) == 0]
    if component_name not in SILO_REGISTRY:
        status = "UNKNOWN_COMPONENT"
    elif missing:
        status = "INCOMPLETE (missing: %s)" % ", ".join(missing[:4])
    elif empty:
        status = "EMPTY_FILES (empty: %s)" % ", ".join(empty[:4])
    else:
        status = "READY"
    return {"status": status, "files_expected": len(files), "missing": missing, "empty": empty}


def initialize_engine():
    """Report the real state to the Bridge Governor. Returns the number of problems found."""
    print(f"--- Verifying {ENGINE_ID} (files on disk) ---")
    problems = 0
    for component in SILO_REGISTRY.keys():
        assessment = perform_health_assessment(component)
        problems += 0 if assessment["status"] == "READY" else 1
        deck.report_status(ENGINE_ID, component, assessment)
        print(f"Component: {component} | Status: {assessment['status']}")
    for area, names in PLANNED.items():
        deck.report_status(ENGINE_ID, area, {"status": "PLANNED", "files": names})
        print(f"Component: {area} | Status: PLANNED (no files yet)")
    for gov_key, gov_file in NEXXUS_GOVERNANCE.items():
        ok = os.path.isfile(os.path.join(HERE, gov_file))
        optional = gov_key == "engine_snippet_review"        # only a peer-reviewer engine carries the review snippet
        label = "PRESENT" if ok else ("NOT_INSTALLED (optional)" if optional else "MISSING")
        problems += 0 if (ok or optional) else 1
        deck.report_status(ENGINE_ID, f"NEXXUS_Governance_{gov_key}", {"status": label, "file": gov_file})
        print(f"NEXXUS Governance: {gov_key} ({gov_file}) - {label}")
    deck.report_status(ENGINE_ID, "SYSTEM", "ALL_FILES_PRESENT" if not problems else "INCOMPLETE: %d issue(s)" % problems)
    return problems


if __name__ == "__main__":
    initialize_engine()
