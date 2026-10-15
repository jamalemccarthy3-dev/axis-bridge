# SECURITY_USERPREFERENCE_REQUEST
# Purpose: The dedicated line for Security to fetch context for data packaging.

from lib import user_preference
import validator

def fetch_security_context(auth_token, preference_key):
    # Only Security can ask for these specific packaging preferences
    if validator.validate_access("SECURITY_WATCHTOWER", auth_token):
        return user_preference.fetch_value(preference_key)
    return "ACCESS_DENIED"
