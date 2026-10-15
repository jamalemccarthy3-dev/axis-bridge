# AUDITOR_PATROL_RADIO_REQUEST
# Purpose: The dedicated line for the Auditor to request radio data.

from lib import patrol_radio as patrolradio
import validator

def request_radio_data(auth_token):
    if validator.validate_access("AUDITOR_BRAIN", auth_token):
        return patrolradio.get_signal()
    return "ACCESS_DENIED"
