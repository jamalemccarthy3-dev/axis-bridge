"""Shared locations for the auditor. Everything is derived from where the engine lives, so it works on any machine."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
INTERFACE = os.path.dirname(HERE)                    # auditor_interface/
ENGINE = os.path.dirname(INTERFACE)                  # axis-integrity/
SILO_ROOT = os.environ.get("AXIS_INTEGRITY_SILO_ROOT") or os.path.dirname(ENGINE)   # silo_vault/: its axis-* folders are the engines the auditor watches (tests point this elsewhere)
LOGS = os.environ.get("AXIS_INTEGRITY_LOGS") or os.path.join(ENGINE, "logs")
AUDITOR_PY = os.path.join(ENGINE, "lib", "auditor.py")
