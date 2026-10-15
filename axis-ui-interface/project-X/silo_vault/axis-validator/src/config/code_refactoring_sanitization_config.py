"""
Configuration parameters for the code refactoring sanitization module.
Defines AST mutation limits, token scrubbing rules, and sanitization strictness.
"""

CODE_SANITIZATION_CONFIG = {
    "module_name": "code_refactoring_sanitization",
    "version": "1.0.0",
    "sanitization_mode": "strict_scrubbing",
    "parameters": {
        "strip_unsafe_evals": True,
        "max_ast_mutation_depth": 15,
        "quarantine_unrecognized_tokens": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}