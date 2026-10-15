"""Lets src/ layers write `import silo_inventory_map`: the real module is auditor_interface/silo_inventory_map.py (loaded through lib/layers.py)."""
from lib.layers import load as _load

_mod = _load("auditor_interface", "silo_inventory_map")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
