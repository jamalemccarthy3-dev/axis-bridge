#!/usr/bin/env python3

"""
master_config.py
Master configuration schema and integration
registry for the AXIS sovereign
infrastructure and NEXXUS intelligence layer.
Unifies all utility paths, ports,
silos, and system settings into a single
authoritative reference.
"""

from pathlib import Path

# ## 1. IDENTIFY THE SILO
ENGINE_ID = "axis-bridge"

# ## 1.5 NEXXUS GOVERNANCE TRACKING
NEXXUS_GOVERNANCE = {
    "mesh": "mesh.py",
    "engine_snippet_review": "engine_snippet_review.py"
}

# Base Paths
BASE_DIR = Path(__file__).parent.resolve()
BIN_DIR = BASE_DIR / "bin"
UTILITIES_DIR = BASE_DIR / "utilities"
SILOS_DIR = BASE_DIR / "silos"
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"
FILES_DIR = BASE_DIR / "files"

# Silo Sub-paths (including expanded Research silo structure)
SILO_PATHS = {
    "Business": SILOS_DIR / "Business",
    "Trading": SILOS_DIR / "Trading",
    "Research": SILOS_DIR / "Research",
    "Research_Hypotheses": SILOS_DIR / "Research" / "hypotheses",
    "Research_Datasets": SILOS_DIR / "Research" / "raw-datasets",
    "Research_Simulations": SILOS_DIR / "Research" / "simulations",
    "Research_Synthesis": SILOS_DIR / "Research" / "synthesis",
    "Custom": SILOS_DIR / "Custom"
}

# Network and Server Configuration
NETWORK_CONFIG = {
    "bind_address": "0.0.0.0",
    "port": 5000,
    "wireguard_interface": "wg0",
    "access_point_ssid": "AXIS-Sovereign-AP"
}

# ## AXIS VAULT CONTAINER (axis_vault_container.py reads this as a plain constant; it never imports this file).
# Drop axis_vault_container.py into any folder and run it: it claims that folder, provisions <folder>/AXIS_SECURE_VAULT and mirrors every file in the folder into it with a verified, byte-accurate copy.
# With no master_config.py beside the file the container uses these same values as its built-in defaults. It is isolation + verified copies + tamper evidence; it is NOT encryption or access control.
AXIS_VAULT_CONFIG = {
    "enabled": True,
    "vault_folder_name": "AXIS_SECURE_VAULT",
    "log_file": "vault_activity.log",             # hash-chained activity log, written in the governed folder
    "status_file": "vault_status.json",           # health + counters for telemetry loops (green / yellow / red), written atomically
    "poll_interval_seconds": 5,                   # how often the governed folder is looked at; a file is copied once it has stopped changing
    "heartbeat_seconds": 60,                      # how often a HEALTH line is printed on the terminal and the status file refreshed
    "max_file_mb": 2048,                          # larger files are skipped and reported, never half-copied
    "verify_after_copy": True,                    # read each copy back and compare SHA-256 before it is put in place
    "keep_versions": 0,                           # 0 = keep every earlier version of a changed file; N = keep the newest N (older ones are deleted)
    "mirror_to": [],                              # extra EXISTING folders (another drive, a cloud folder, the dashboard core mount): each gets its own verified copy
    "exclude_patterns": ["*.tmp", "*.part", "*.crdownload", "~$*", ".~lock*", "desktop.ini", ".DS_Store", "Thumbs.db", "*.pyc", "*.swp", "*.log.lock"],
    "exclude_dirs": [".git", "__pycache__", "node_modules", ".venv"],
}

# Utility Module Registry mapping names to relative script paths
UTILITY_REGISTRY = {
    "cloud_server": BASE_DIR / "axis_cloud_server.py",
    "daemon_mgr": BASE_DIR / "axis_daemon_mgr.py",
    "vault_core": BASE_DIR / "axis_vault_core.py",
    "tunnel_bridge": BASE_DIR / "axis_tunnel_bridge.py",
    "router_bridge": BASE_DIR / "axis_router_bridge.py",
    "pulse": BASE_DIR / "axis_pulse.py",
    "cert_mgr": BASE_DIR / "axis_cert_mgr.py",
    "backup_mgr": BASE_DIR / "axis_backup_mgr.py",
    "audit_mgr": BASE_DIR / "axis_audit_mgr.py",
    "ap_mgr": BASE_DIR / "axis_ap_mgr.py",
    "vault_container": BASE_DIR / "axis_vault_container.py"
}

def export_master_config():
    """Compiles and returns the entire system configuration profile."""
    config = {
        "infrastructure": "AXIS",
        "orchestrator": "NEXXUS",
        "base_directory": str(BASE_DIR),
        "directories": {str(k): str(v) for k, v in SILO_PATHS.items()},
        "network": NETWORK_CONFIG,
        "utilities": {name: str(path) for name, path in UTILITY_REGISTRY.items()},
        "nexxus_governance": NEXXUS_GOVERNANCE
    }
    return config

if __name__ == "__main__":
    import json
    print(json.dumps(export_master_config(), indent=2))#!/usr/bin/env python3
"""
master_config.py
Master configuration schema and integration registry for the AXIS sovereign 
infrastructure and NEXXUS intelligence layer. Unifies all utility paths, ports, 
silos, and system settings into a single authoritative reference.
"""

from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).parent.resolve()
BIN_DIR = BASE_DIR / "bin"
UTILITIES_DIR = BASE_DIR / "utilities"
SILOS_DIR = BASE_DIR / "silos"
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"
FILES_DIR = BASE_DIR / "files"

# Silo Sub-paths (including expanded Research silo structure)
SILO_PATHS = {
    "Business": SILOS_DIR / "Business",
    "Trading": SILOS_DIR / "Trading",
    "Research": SILOS_DIR / "Research",
    "Research_Hypotheses": SILOS_DIR / "Research" / "hypotheses",
    "Research_Datasets": SILOS_DIR / "Research" / "raw-datasets",
    "Research_Simulations": SILOS_DIR / "Research" / "simulations",
    "Research_Synthesis": SILOS_DIR / "Research" / "synthesis",
    "Custom": SILOS_DIR / "Custom"
}

# Network and Server Configuration
NETWORK_CONFIG = {
    "bind_address": "0.0.0.0",
    "port": 5000,
    "wireguard_interface": "wg0",
    "access_point_ssid": "AXIS-Sovereign-AP"
}

# Utility Module Registry mapping names to relative script paths
UTILITY_REGISTRY = {
    "cloud_server": BASE_DIR / "axis_cloud_server.py",
    "daemon_mgr": BASE_DIR / "axis_daemon_mgr.py",
    "vault_core": BASE_DIR / "axis_vault_core.py",
    "tunnel_bridge": BASE_DIR / "axis_tunnel_bridge.py",
    "router_bridge": BASE_DIR / "axis_router_bridge.py",
    "pulse": BASE_DIR / "axis_pulse.py",
    "cert_mgr": BASE_DIR / "axis_cert_mgr.py",
    "backup_mgr": BASE_DIR / "axis_backup_mgr.py",
    "audit_mgr": BASE_DIR / "axis_audit_mgr.py",
    "ap_mgr": BASE_DIR / "axis_ap_mgr.py"
}

def export_master_config():
    """Compiles and returns the entire system configuration profile."""
    config = {
        "infrastructure": "AXIS",
        "orchestrator": "NEXXUS",
        "base_directory": str(BASE_DIR),
        "directories": {str(k): str(v) for k, v in SILO_PATHS.items()},
        "network": NETWORK_CONFIG,
        "utilities": {name: str(path) for name, path in UTILITY_REGISTRY.items()},
        "vault_container": AXIS_VAULT_CONFIG
    }
    return config

if __name__ == "__main__":
    import json
    print(json.dumps(export_master_config(), indent=2))