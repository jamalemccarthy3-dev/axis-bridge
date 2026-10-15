# AUDITOR_SELFHEALER_REQUEST
# Purpose: Allows the Auditor to trigger healing if it detects a system anomaly.

from lib import self_healer
import validator

def trigger_healing(auth_token):
    if validator.validate_access("AUDITOR_BRAIN", auth_token):
        return self_healer.initiate_recovery()
    return "ACCESS_DENIED"
