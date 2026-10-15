# VALIDATOR_UTILITY: The Gatekeeper v1.0
# District: Processor/Validator
# Purpose: Orchestrates the validation process and reports to Auditor.
import validator_tool as tool


def validate_data(data):
    """True when `data` is a string that meets the entry rules (length and allowed characters - see validator_config). Violations are logged without the data."""
    return tool.check_string(data)


def validate_access(user_id, token):
    """True only if `token` is a valid governance token for `user_id` (auth_protocol: HMAC bound to that persona, locked after repeated failures) and both are well-formed.
    Nobody is authorised without the governance secret being configured."""
    import integrity_store
    try:
        integrity_store.safe_name(user_id)           # a persona id is a plain name: letters, digits, '-', '_', '.' (the 8-character rule is for tokens and data)
    except ValueError:
        return False
    if not isinstance(token, str) or not token:
        return False
    import auth_protocol
    return bool(auth_protocol.authorize_request(token, user_id))
