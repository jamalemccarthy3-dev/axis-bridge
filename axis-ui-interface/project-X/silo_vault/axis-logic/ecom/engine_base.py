# silo_ecom/engine_base.py
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "lib") not in sys.path:
    sys.path.append(os.path.join(_ROOT, "lib"))
from manager import load  # noqa: E402

bridge = load("engine_base").create_bridge("ECOM")
