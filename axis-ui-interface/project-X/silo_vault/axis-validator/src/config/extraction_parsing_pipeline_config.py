"""
Configuration parameters for the extraction parsing pipeline module.
Defines parsing stream limits, syntax strictness levels, and error tolerance thresholds.
"""

EXTRACTION_PIPELINE_CONFIG = {
    "module_name": "extraction_parsing_pipeline",
    "version": "1.0.0",
    "pipeline_mode": "strict_extraction",
    "parameters": {
        "max_payload_size_mb": 10,
        "strict_syntax_check": True,
        "quarantine_malformed_streams": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}