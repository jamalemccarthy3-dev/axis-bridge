"""Lets src/ layers write `import validator`: the real module is auditor_interface/validator.py (loaded through lib/layers.py)."""
from lib.layers import load as _load

_mod = _load("auditor_interface", "validator")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
