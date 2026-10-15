import os
import sys

_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)               # the engine's own folder, so this file also runs from config/

from bridge_diagnostic import deck

# 1. IDENTIFY THE SILO
ENGINE_ID = "AXIS_SWEEP"

# 1.5 NEXXUS GOVERNANCE TRACKING
NEXXUS_GOVERNANCE = {
    "mesh": "mesh.py",
    "engine_snippet_review": "engine_snippet_review.py"
}

# 2. DEFINE THE REGISTRY MAP
# Mapping all functional modules from src and libraries from lib
SILO_REGISTRY = {
    "axis_manager": "src/axis-manager",
    "dashbord": "src/dashbord",
    "event_dispatcher": "src/event_dispatcher",
    "feedback_manager": "src/feedback_manager",
    "lineage": "src/lineage",
    "main": "src/main",
    "purge": "src/purge",
    "scheduler": "src/scheduler",
    "throttler": "src/throttler",
    "lib_crypto_vault": "lib/crypto_vault",
    "lib_port_manager": "lib/port_manager"
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
        return os.path.exists(base) or any(os.path.exists(base + ext) for ext in (".py", ".c", ".h", ".json", ".exe", ".js"))   # some registries list names without extensions
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
