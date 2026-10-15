"""
Configuration parameters for the human in the loop audit module.
Defines mandatory review triggers, escalation timeouts, and audit logging policies.
"""

HUMAN_AUDIT_CONFIG = {
    "module_name": "human_in_the_loop_audit",
    "version": "1.0.0",
    "audit_mode": "mandatory_checkpoint",
    "parameters": {
        "require_signoff": True,
        "escalation_timeout_seconds": 300,
        "quarantine_pending_approval": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}