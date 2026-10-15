# VALIDATOR_REQUEST: The Security Checkpoint
# Purpose: Provides a simple interface for any module to request access validation.
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.append(_ROOT)
from lib.layers import load  # noqa: E402


def request_validation(user_id, token):
    """True only if the token is valid for that user (see the auditor interface's validator.validate_access)."""
    return load("auditor_interface", "validator").validate_access(user_id, token)
