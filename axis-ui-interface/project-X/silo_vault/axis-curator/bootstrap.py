"""bootstrap.py - gives the curator's tools the flat import names they were written against.

The *_tool.py files import `<name>_utility` (the engine, which lives in the root script `<name>.py`) and `<name>_config` (in config/).
Importing this module once puts the folders on sys.path and registers those `<name>_utility` aliases, so nothing has to be copied or renamed.
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
GOV = os.path.join(ROOT, "src", "governor")

# ROOT first, so the names `config` and `lib` mean THIS engine's folders (the governor has its own config/ and lib/, which must not shadow them).
# The other folders are only searched for the flat module names the tools use (`verify_integrity_config`, ...).
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
for p in (os.path.join(ROOT, "config"), os.path.join(ROOT, "lib"), os.path.join(GOV, "config"), os.path.join(GOV, "lib")):
    if p not in sys.path:
        sys.path.append(p)

# <import name used by the tool> -> <module that really holds the engine>
UTILITY_ALIASES = {
    "automated_metadata_tagging_utility": "automated_metadata_tagging",
    "checksum_verification_utility": "checksum_verification",
    "curate_input_path_utility": "curate_input_path",
    "denoising_sanitization_utility": "denoising_sanitization",
    "optimize_storage_utility": "optimize_storage",
    "verify_integrity_utility": "verify_integrity",
    "categorization_cataloging_utility": "src.governor.categorization_cataloging_engine",
    "dependency_mapper_utility": "src.governor.dependency_mapper",
    "life_cycle_policy_utility": "src.governor.life_cycle_policy",
    "categorization_cataloging_config": "categorization_cataloging_engine_config",
}
for alias, real in UTILITY_ALIASES.items():
    if alias not in sys.modules:
        try:
            sys.modules[alias] = importlib.import_module(real)
        except Exception:                  # a broken engine shows up in health_report.py, it must not stop the others from loading
            pass
