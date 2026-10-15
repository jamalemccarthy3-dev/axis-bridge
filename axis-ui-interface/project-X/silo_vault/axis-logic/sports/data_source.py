# silo_sports/data_source.py
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "lib") not in sys.path:
    sys.path.append(os.path.join(_ROOT, "lib"))
from manager import load  # noqa: E402

gatekeeper = load("data_source").DataSource("SPORTS")


def connect(path):
    """Open this silo's data stream (a .json or .csv file). -> True when the gatekeeper accepts it; nothing runs at import."""
    return gatekeeper.connect(path)


def fetch():
    return gatekeeper.fetch()
