"""
Configuration parameters for the direct API router module.
Defines endpoint routing rules, rate limit caps, and direct proxy security policies.
"""

DIRECT_API_ROUTER_CONFIG = {
    "module_name": "direct_api_router",
    "version": "1.0.0",
    "router_mode": "direct_proxy",
    "parameters": {
        "max_requests_per_minute": 120,
        "require_auth_header": True,
        "enforce_tls_tunnel": True,
    },
    "logging_policy": {
        "log_level": "INFO",
        "audit_trail_enabled": True,
    },
}