"""
Master Configuration Test Suite (`tests/test_master_config.py`) for the AXIS Validator Suite.
Validates structural integrity, parameter consistency, and schema completeness across the master config manifest.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration for sovereign modules
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from master_config import AXIS_MASTER_CONFIG

def test_master_config_structure() -> bool:
    """Verifies that the master configuration manifest contains all required root keys and subsystems."""
    print("Executing AXIS Master Configuration Integrity Test...")

    required_roots = ["system_identity", "orchestrator_parameters", "subsystem_registry", "logging_policy"]
    for root in required_roots:
        if root not in AXIS_MASTER_CONFIG:
            print(f"[ERROR] Missing required root configuration key: {root}")
            return False

    subsystems = AXIS_MASTER_CONFIG.get("subsystem_registry", {})
    expected_subsystem_count = 21

    if len(subsystems) < expected_subsystem_count:
        print(f"[ERROR] Subsystem registry incomplete. Found {len(subsystems)}, expected at least {expected_subsystem_count}.")
        return False

    print(f"[SUCCESS] Master configuration validated. Total registered subsystems: {len(subsystems)}")
    return True

def test_master_config_parameters() -> bool:
    """Verifies that critical zero-trust parameters and security flags are correctly enabled."""
    identity = AXIS_MASTER_CONFIG.get("system_identity", {})
    params = AXIS_MASTER_CONFIG.get("orchestrator_parameters", {})

    assert identity.get("architecture") == "NEXXUS_SOVEREIGN", "Architecture mismatch in config."
    assert params.get("enforce_zero_trust") is True, "Zero-trust enforcement is disabled in master config."
    assert params.get("quarantine_on_failure") is True, "Quarantine protocols are disabled in master config."

    print("[SUCCESS] Operational parameters and zero-trust flags verified successfully.")
    return True

if __name__ == "__main__":
    passed_structure = test_master_config_structure()
    passed_params = test_master_config_parameters()

    if passed_structure and passed_params:
        print("\n[DIAGNOSTIC COMPLETE] Master Configuration Test Suite PASSED.")
    else:
        print("\n[CRITICAL ERROR] Master Configuration Test Suite FAILED.")
        sys.exit(1)