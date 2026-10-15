import os
import sys

from bridge_diagnostic import deck

# 1. IDENTIFY THE SILO
ENGINE_ID = "axis-port"

# 1.5 NEXXUS GOVERNANCE TRACKING
NEXXUS_GOVERNANCE = {
    "mesh": "mesh.py",
    "engine_snippet_review": "engine_snippet_review.py"
}

# 2. DEFINE THE REGISTRY MAP
SILO_REGISTRY = {
    "root": [
        "bridge_diagnostic.py",
        "master_config.py",
        "master_test.py",
        "system_core.exe",
        "a.exe"
    ],
    "build": [
        "actuator.o",
        "main.o",
        "memory_purger.o",
        "stability_watchdog.o",
        "workflow_manager.o"
    ],
    "config": [
        "manifest_settings.conf",
        "safety_thresholds.conf",
        "system_env.conf"
    ],
    "lib": [
        "actuator.c",
        "actuator.h",
        "memory_purger.c",
        "memory_purger.h",
        "stability_watchdog.c",
        "stability_watchdog.h"
    ],
    "src": [
        "actuator_interface.c",
        "actuator_interface.h",
        "main.c",
        "main.h",
        "workflow_manager.c",
        "workflow_manager.h"
    ],
    "pulse_channel": {
        "path": "pipeline_pulse.json",
        "protocol": "read_write"
    }
}


def _engine_root():
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    for _ in range(3):
        if os.path.isfile(os.path.join(d, "bridge_diagnostic.py")):
            return d
        d = os.path.dirname(d)
    return here


def _engine_root():
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    for _ in range(3):
        if os.path.isfile(os.path.join(d, "bridge_diagnostic.py")):
            return d
        d = os.path.dirname(d)
    return here


def perform_health_assessment(component_name):
    """A real check, not a promise: every file or folder this component lists must exist on disk. Nothing is run or compiled."""
    spec = SILO_REGISTRY.get(component_name)
    root = _engine_root()
    if spec is None:
        return {"status": "UNKNOWN_COMPONENT", "missing": [], "path": "UNKNOWN"}
    if isinstance(spec, dict):
        paths = [spec["path"]] if "path" in spec else []
    elif isinstance(spec, str):
        paths = [spec]
    elif component_name == "root":
        paths = list(spec)
    else:
        paths = [component_name + "/" + n for n in spec]
    def present(p):
        base = os.path.join(root, p)
        return os.path.exists(base) or any(os.path.exists(base + ext) for ext in (".py", ".c", ".h", ".json", ".exe"))   # some registries list names without extensions
    missing = [p for p in paths if not present(p)]
    return {"status": "READY" if not missing else "INCOMPLETE (missing: %s)" % ", ".join(missing[:4]), "files_expected": len(paths), "missing": missing, "path": spec if isinstance(spec, str) else component_name}


def initialize_engine():
    """Report the real state to the Bridge Governor. Returns the number of problems found."""
    print(f"--- Verifying {ENGINE_ID} (files on disk; nothing is run or compiled) ---")
    problems = 0
    for component in SILO_REGISTRY.keys():
        assessment = perform_health_assessment(component)
        problems += 0 if assessment["status"] == "READY" else 1
        deck.report_status(ENGINE_ID, component, assessment)
        print(f"Component: {component} | Status: {assessment['status']}")
    root = _engine_root()
    for gov_key, gov_file in globals().get("NEXXUS_GOVERNANCE", {"mesh": "mesh.py"}).items():
        present = os.path.isfile(os.path.join(root, gov_file))
        optional = gov_key == "engine_snippet_review"        # only an engine that acts as a peer reviewer carries the review snippet
        label = "PRESENT" if present else ("NOT_INSTALLED (optional)" if optional else "MISSING")
        problems += 0 if (present or optional) else 1
        deck.report_status(ENGINE_ID, f"NEXXUS_Governance_{gov_key}", {"status": label, "file": gov_file})
        print(f"NEXXUS Governance: {gov_key} ({gov_file}) - {label}")
    deck.report_status(ENGINE_ID, "SYSTEM", "ALL_FILES_PRESENT" if not problems else "INCOMPLETE: %d issue(s)" % problems)
    return problems


if __name__ == "__main__":
    sys.exit(1 if initialize_engine() else 0)
