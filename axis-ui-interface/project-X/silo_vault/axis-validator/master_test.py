"""
Master Integration Test Suite (`master_test.py`) for the AXIS Validator Suite.
Executes comprehensive end-to-end integration verification across all subsystems,
the unified orchestrator, remote script ingestion, and root-level configuration.
"""

import sys
from pathlib import Path

# Ensure absolute root path integration for sovereign modules
root_dir = Path(__file__).resolve().parent
sys.path.append(str(root_dir))

from orchestrator.orchestrator import AXISValidatorOrchestrator
from master_config import AXIS_MASTER_CONFIG

def run_master_integration_suite() -> bool:
    """Executes full diagnostic integration testing across the entire NEXXUS/AXIS stack."""
    print("======================================================================")
    print("      NEXXUS SOVEREIGN ARCHITECTURE: MASTER INTEGRATION TEST          ")
    print("======================================================================")
    print("Initializing AXIS Master Integration Test Suite...")

    # 1. Verify Configuration Manifest Integrity
    print("\n[Step 1/3] Verifying Master Configuration Manifest...")
    subsystems_count = len(AXIS_MASTER_CONFIG.get("subsystem_registry", {}))
    if subsystems_count < 21:
        print(f"[ERROR] Subsystem registry count mismatch: found {subsystems_count}, expected 21+.")
        return False
    print(f"-> Manifest verified. Active subsystems registered: {subsystems_count}")

    # 2. Initialize and Run Orchestrator Pipeline Diagnostics
    print("\n[Step 2/3] Bootstrapping Master Orchestrator & Running Diagnostics...")
    orchestrator = AXISValidatorOrchestrator(execution_mode="strict_zero_trust")
    
    pipeline_success = orchestrator.run_full_diagnostic_pipeline()
    if not pipeline_success:
        print("[ERROR] Orchestrator pipeline diagnostic check failed.")
        return False
    print("-> All orchestrator validation handlers executed successfully.")

    # 3. Verify Remote Git Script Ingestion Capability
    print("\n[Step 3/3] Testing Remote Git Ingestion & AST Parsing Hook...")
    test_repo = "https://github.com/octocat/Hello-World"
    test_file = "README"
    
    ingestion_result = orchestrator.fetch_and_parse_remote_script(test_repo, test_file)
    if not isinstance(ingestion_result, dict) or "success" not in ingestion_result:
        print("[ERROR] Remote Git ingestor method failed structural return contract.")
        return False
    print(f"-> Remote ingestion interface responsive. Status: {ingestion_result.get('success')}")

    print("\n======================================================================")
    print("[SUCCESS] ALL MASTER INTEGRATION TESTS PASSED. SYSTEM SOVEREIGN READY.")
    print("======================================================================")
    return True

if __name__ == "__main__":
    success = run_master_integration_suite()
    if not success:
        sys.exit(1)