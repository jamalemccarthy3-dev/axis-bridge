# SECURITY_SELFHEALER_REQUEST
# Purpose: Allows the Security Watchtower to trigger healing protocols.

from lib import self_healer
import validator

def trigger_healing(auth_token):
    if validator.validate_access("SECURITY_WATCHTOWER", auth_token):
        return self_healer.initiate_recovery()
    return "ACCESS_DENIED"