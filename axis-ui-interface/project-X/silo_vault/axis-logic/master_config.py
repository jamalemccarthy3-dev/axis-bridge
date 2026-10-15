import os
import sys

from bridge_diagnostic import deck

# ## 1. IDENTIFY THE SILO
ENGINE_ID = "axis-logic"

# 1.5 NEXXUS GOVERNANCE TRACKING
NEXXUS_GOVERNANCE = {
    "mesh": "mesh.py",
    "engine_snippet_review": "engine_snippet_review.py"
}

# ## 2. DISTRIBUTE UNIVERSAL TOOLS & LIB REGISTRY
SILO_REGISTRY = {
    "root": [
        "main.py",
        "master_run.py",
        "bridge_diagnostic.py",
        "system_audit.log"
    ],
    "lib": [
        "__init__.py",
        "fetcher.py",
        "forensic_ledger.py",
        "manager.py",
        "markets.py",
        "math_utils.py",
        "memory.py",
        "port.py",
        "probability.py",
        "watchdog.py"
    ],
    "config": [
        "__init__.py",
        "env_vars.py",
        "logging_config.py",
        "settings.py",
        "silo_params.py",
        "system.py",
        "tickers.py"
    ],
    "interface": [
        "__init__.py",
        "controller.py",
        "voice_engine.py"
    ],
    "ecom": [
        "__init__.py",
        "data_source.py",
        "ecom.py",
        "engine_base.py",
        "entropy.py",
        "feedback.py",
        "risk.py",
        "signal.py",
        "stratagy.py",
        "test_status.py",
        "thershold.py"
    ],
    "logs": [
        "__init__.py",
        "data_source.py",
        "engine_base.py",
        "entropy.py",
        "feedback.py",
        "logs.py",
        "risk.py",
        "signal.py",
        "stratagy.py",
        "test_status.py",
        "thershold.py"
    ],
    "operations": [
        "__init__.py",
        "bridge_connector.py",
        "build_governor.py",
        "dispatcher.py",
        "emergency_halt.py",
        "feedback_loop.py",
        "integrity_checker.py",
        "session_manager.py",
        "status_reporter.py",
        "stream_processor.py",
        "task_scheduler.py"
    ],
    "sports": [
        "__init__.py",
        "data_source.py",
        "engine_base.py",
        "entropy.py",
        "feedback.py",
        "risk.py",
        "signal.py",
        "sports.py",
        "stratagy.py",
        "test_status.py",
        "thershold.py"
    ],
    "stocks": [
        "__init__.py",
        "data_source.py",
        "engine_base.py",
        "entropy.py",
        "feedback.py",
        "risk.py",
        "signal.py",
        "stocks.py",
        "stratagy.py",
        "test_status.py",
        "thershold.py"
    ],
    "src": [
        "__init__.py"
    ],
    "src/silo_manager": [
        "__init__.py",
        "pipeline.py",
        "data_source.py",
        "engine_base.py",
        "entropy.py",
        "feedback.py",
        "risk.py",
        "signal.py",
        "strategy.py",
        "threshold.py"
    ],
    "src/silo_manager/governor": [
        "__init__.py",
        "worker.py"
    ]
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
