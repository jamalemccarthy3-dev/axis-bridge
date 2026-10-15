# INTEGRITY_CHECK_CONFIG: Pre-Flight Checklist.
MANDATORY_DISTRICTS = ["AUDITOR", "SECURITY", "BRIDGE"]
# Ensure these files exist/are reachable before startup
REQUIRED_AUTH_MODULES = ["validator.py", "session_manager.py"]
ALLOW_PARTIAL_START = False 
