"""Lets src/security write `import forensic_dump`: the real module is auditor_interface/forensic_dump.py (loaded through lib/layers.py)."""
from lib.layers import load as _load

_mod = _load("auditor_interface", "forensic_dump")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
