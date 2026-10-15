"""
Configuration parameters for the repository miner module.
Defines scan depth boundaries, file exclusion filters, and metadata extraction rules.
"""

REPOSITORY_MINER_CONFIG = {
    "module_name": "repository_miner",
    "version": "1.0.0",
    "mining_mode": "deep_scan",
    "parameters": {
        "max_scan_depth": 10,
        "exclude_hidden_files": True,
        "allow_compiled_bytecode": False,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}