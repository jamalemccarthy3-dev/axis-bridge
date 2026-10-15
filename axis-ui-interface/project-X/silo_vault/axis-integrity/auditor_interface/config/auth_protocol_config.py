# AUTH_PROTOCOL_CONFIG: Security Thresholds
# Purpose: Define session expiration and lock-out.

REQUIRE_MFA = False                 # no second factor exists: a token is checked   scan:ok
SESSION_TIMEOUT_SECONDS = 300
MAX_FAILED_ATTEMPTS = 3             # after this many wrong tokens a persona is locked until the process restarts
SECRET_ENV = "NEXXUS_GOVERNANCE_SECRET"
