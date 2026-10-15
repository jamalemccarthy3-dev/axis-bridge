"""health_report.py - checks axis-curator for real: every script, config and tool exists, imports, and every tool can be created.
Run: python health_report.py        Exit code 0 only when nothing is broken."""
import importlib
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
import bootstrap  # noqa: E402,F401
from master_config import SILO_REGISTRY  # noqa: E402

TOOLS = [  # (module, class)
    ("automated_metadata_tagging_tool", "AutomatedMetadataTaggingTool"), ("checksum_verification_tool", "ChecksumVerificationTool"),
    ("curate_input_path_tool", "CurateInputPathTool"), ("denoising_sanitization_tool", "DenoisingSanitizationTool"),
    ("master_interface_utility_tool", "MasterInterfaceTool"), ("optimize_storage_tool", "OptimizeStorageTool"),
    ("orchestrator_utility_tool", "OrchestratorTool"), ("verify_integrity_tool", "VerifyIntegrityTool"),
    ("categorization_cataloging_engine_tool", "CategorizationCatalogingTool"), ("dependency_mapper_tool", "DependencyMapperTool"),
    ("life_cycle_policy_tool", "LifeCyclePolicyTool"),
]


def problems():
    out = []
    gov = os.path.join(ROOT, "src", "governor")
    for key, base in (("root_floor_scripts", ROOT), ("config_pairings", os.path.join(ROOT, "config")), ("governor_src", gov)):
        for f in SILO_REGISTRY[key]:
            if not os.path.isfile(os.path.join(base, f)):
                out.append(("MISSING", f))
                continue
            try:
                importlib.import_module(("src.governor." if key == "governor_src" else "") + f[:-3])
            except BaseException as e:
                out.append(("IMPORT_ERROR", "%s: %s: %s" % (f, type(e).__name__, str(e)[:100])))
    for mod, cls in TOOLS:
        try:
            getattr(importlib.import_module(mod), cls)()
        except BaseException as e:
            out.append(("TOOL_ERROR", "%s.%s: %s: %s" % (mod, cls, type(e).__name__, str(e)[:100])))
    return out


def main():
    ps = problems()
    for kind, what in ps:
        print("  %-13s %s" % (kind, what))
    print("\n%s" % ("ALL SCRIPTS, CONFIGS AND TOOLS LOAD" if not ps else "%d problem(s)" % len(ps)))
    return 1 if ps else 0


if __name__ == "__main__":
    sys.exit(main())
