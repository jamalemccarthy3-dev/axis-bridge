# SECURITY_PATROLRADIO_REQUEST
# Purpose: The dedicated line for the Security Watchtower to request radio data.

from lib import patrol_radio as patrolradio
import validator

def request_radio_data(auth_token):
    if validator.validate_access("SECURITY_WATCHTOWER", auth_token):
        return patrolradio.get_signal()
    return "ACCESS_DENIED"
