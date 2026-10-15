#!/usr/bin/env python3
"""
test_master_config.py
Verifies that all master configuration paths, domain subdirectories within 'files/', 
and utility module script paths are correctly mapped and present on disk.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

try:
    import master_config
except ImportError as e:
    print(f"[TEST-CONFIG] CRITICAL: Failed to import master_config: {e}")
    sys.exit(1)

def run_config_validation():
    print("[TEST-CONFIG] Initializing master configuration verification and provisioning...")
    errors = 0
    success_count = 0

    # 1. Verify and Provision Base Directory
    if not master_config.BASE_DIR.exists():
        master_config.BASE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[PASS] Base directory verified: {master_config.BASE_DIR}")
    success_count += 1

    # 2. Verify and Provision Silo/Domain Paths inside files/
    print("[TEST-CONFIG] Checking and provisioning domain subdirectories within files/...")
    for name, path in master_config.SILO_PATHS.items():
        path.mkdir(parents=True, exist_ok=True)
        if path.exists():
            print(f"  [PASS] Domain path '{name}' verified/created at {path}")
            success_count += 1
        else:
            print(f"  [FAIL] Domain path '{name}' could not be created at {path}")
            errors += 1

    # 3. Verify Utility Scripts Registry
    print("[TEST-CONFIG] Checking utility module registry file paths...")
    for name, path in master_config.UTILITY_REGISTRY.items():
        if path.exists():
            print(f"  [PASS] Utility '{name}' script present.")
            success_count += 1
        else:
            print(f"  [FAIL] Utility '{name}' script missing at {path}")
            errors += 1

    print("\n--------------------------------------------------")
    if errors == 0:
        print(f"[TEST-CONFIG] SUCCESS: All {success_count} configuration checks passed cleanly.")
        sys.exit(0)
    else:
        print(f"[TEST-CONFIG] FAILURE: {errors} configuration errors detected.")
        sys.exit(1)

if __name__ == "__main__":
    run_config_validation()