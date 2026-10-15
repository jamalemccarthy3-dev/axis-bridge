# Pure Handshake Configuration Description
# No tool processing dependencies - purely environmental parameters

HANDSHAKE_CONFIG = {
"module_name": "AXIS_UI_DELIVERY_PORT",
"protocol_version": "1.0.0",
"timeout_ms": 5000,
"security_mode": "SOVEREIGN_CHALLENGE",
"target_silo": "DELIVERY_CORE",

# Structural flags for validation
"expected_components": [
"AuthTool",
"DispatchTool",
"LogTool"
]
}