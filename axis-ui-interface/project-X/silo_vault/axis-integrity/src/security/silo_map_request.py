# SILO_MAP_REQUEST: The Atlas Request
# Purpose: Provides a simple interface for the Auditor to ask for the system map.
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.append(_ROOT)
from lib.layers import load  # noqa: E402


def get_system_map(auditor_id, auth_token):
    """-> the inventory snapshot ({"authorized": bool, "new", "missing", "engines"}). Without a valid token nothing is revealed: {"authorized": False}."""
    return load("auditor_interface", "silo_inventory_map").request_inventory_snapshot(auditor_id, auth_token)
