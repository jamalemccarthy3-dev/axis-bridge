import os
import sys

from bridge_diagnostic import deck

ENGINE_ID = "axis-triage"

# The grid's own settings (it used to be a bare dict that no code could import)
GRID_CONFIG = {
    "grid_version": "1.1",
    "system_settings": {
        "auto_discover": True,
        "project_prefix": "Project_",
        "log_path": "./axis_audit_log.txt",
        "diagnostic_link": "./axis_audit_log.txt"
    },
    "bridge_diagnostics": {
        "check_interval": 30,
        "health_threshold": "stable",
        "alert_on_failure": True,
        "diagnostic_active_modes": ["combat", "logistics", "story"]
    },
    "operational_nodes": {
        "dynamic_registry_path": "./",
        "status_check_enabled": True,
        # NEXXUS Governance & Verification Tracking
        "nexxus_governance": {
            "mesh": "mesh.py",
            "engine_snippet_review": "engine_snippet_review.py",
            "audit_enabled": True
        },
        "pipeline": {
            "search_engine": "axis_search_engine",
            "triage_gate": "axis_triage",
            "llm_sink": "axis_llm"
        }
    },
    "runtime_parameters": {
        "execution_mode": "parallel",
        "refresh_rate_seconds": 60,
        "max_concurrent_tasks": 5
    }
}

NEXXUS_GOVERNANCE = {
    "mesh": "mesh.py",
    "engine_snippet_review": "engine_snippet_review.py"
}

SILO_REGISTRY = {
    "root": ["main.py", "grid_controller.py", "sanatizer.py", "sync_manager.py", "task_runner.py", "triage_gate.py",
             "master_config.py", "master_test.py", "config_map.json", "bridge_diagnostic.py", "mesh.py"],
    "lib": ["__init__.py", "_cfg.py", "grid_controller_tool.py", "sanatizer_tool.py", "sync_manager_tool.py", "task_runner_tool.py", "triage_gate_tool.py"],
    "config": ["__init__.py", "grid_controller_config.py", "sanatizer_config.py", "sync_manager_config.py", "task_runner_config.py", "triage_gate_config.py"],
}


def _engine_root():
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    for _ in range(3):
        if os.path.isfile(os.path.join(d, "bridge_diagnostic.py")):
            return d
        d = os.path.dirname(d)
    return here


def perform_health_assessment(component_name):
    """A real check, not a promise: every file or folder this component lists must exist on disk. Nothing is run."""
    spec = SILO_REGISTRY.get(component_name)
    root = _engine_root()
    if spec is None:
        return {"status": "UNKNOWN_COMPONENT", "missing": [], "path": "UNKNOWN"}
    paths = list(spec) if component_name == "root" else [component_name + "/" + n for n in spec]
    missing = [p for p in paths if not os.path.exists(os.path.join(root, p))]
    return {"status": "READY" if not missing else "INCOMPLETE (missing: %s)" % ", ".join(missing[:4]), "files_expected": len(paths), "missing": missing, "path": component_name}


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
    for gov_key, gov_file in NEXXUS_GOVERNANCE.items():
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
