#!/usr/bin/env python3
"""
main.py
Master orchestrator entry point for the AXIS sovereign infrastructure 
and NEXXUS intelligence layer. Bootstraps core directories, runs health checks, 
and launches the daemon supervision manager.
"""

import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
DIRECTORIES = [
    BASE_DIR / "bin",
    BASE_DIR / "utilities",
    BASE_DIR / "silos" / "Business",
    BASE_DIR / "silos" / "Trading",
    BASE_DIR / "silos" / "Research",
    BASE_DIR / "silos" / "Custom",
    BASE_DIR / "config" / "certificates",
    BASE_DIR / "config" / "backups",
    BASE_DIR / "logs",
    BASE_DIR / "files"
]

def verify_structure():
    print("[AXIS-MAIN] Verifying sovereign directory architecture...")
    for directory in DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)
    print("[AXIS-MAIN] Directory structure verified and intact.")

def run_pulse_check():
    pulse_script = BASE_DIR / "axis_pulse.py"
    if pulse_script.exists():
        print("[AXIS-MAIN] Running initial hardware pulse check...")
        subprocess.run([sys.executable, str(pulse_script)])

def boot_system():
    verify_structure()
    run_pulse_check()
    
    daemon_mgr = BASE_DIR / "axis_daemon_mgr.py"
    if not daemon_mgr.exists():
        print(f"[AXIS-MAIN] ERROR: Critical daemon manager missing at {daemon_mgr}")
        sys.exit(1)

    print("[AXIS-MAIN] Handing over execution to AXIS Daemon Supervisor under NEXXUS orchestration...")
    try:
        subprocess.run([sys.executable, str(daemon_mgr)], check=True)
    except KeyboardInterrupt:
        print("\n[AXIS-MAIN] Shutdown sequence initiated by operator.")
        sys.exit(0)

if __name__ == "__main__":
    boot_system()