"""
Core Entry Point (`src/main.py`) for the AXIS Validator Suite within the NEXXUS Sovereign Architecture.
Initializes the master orchestrator, executes automated diagnostic checks, and launches runtime services.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration for sovereign modules
sys.path.append(str(Path(__file__).resolve().parent))

from orchestrator.orchestrator import AXISValidatorOrchestrator

def bootstrap_axis_validator_suite() -> None:
    """Bootstraps the AXIS validator suite, initiates the master orchestrator, and executes runtime diagnostics."""
    print("======================================================================")
    print("          NEXXUS SOVEREIGN ARCHITECTURE: AXIS VALIDATOR SUITE         ")
    print("======================================================================")
    print("Bootstrapping core master orchestrator and zero-trust verification pipelines...")

    # Initialize the centralized orchestrator
    orchestrator = AXISValidatorOrchestrator(execution_mode="strict_zero_trust")

    # Execute system-wide end-to-end diagnostics
    system_healthy = orchestrator.run_full_diagnostic_pipeline()

    if not system_healthy:
        print("\n[CRITICAL ERROR] AXIS diagnostic verification failed. Quarantine protocols initiated.")
        sys.exit(1)

    print("\n[SUCCESS] All subsystems verified. AXIS Validator Suite is active and ready.")
    print("======================================================================")

if __name__ == "__main__":
    bootstrap_axis_validator_suite()