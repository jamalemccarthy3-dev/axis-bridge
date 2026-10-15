"""CGI silo diagnostic: every operation's tool class must import, accept its config and offer methods. Run: python test_cgi_silo.py"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

operations = ["asset_registry_loader", "blueprint_compiler_hook", "buffer_governor_bridge", "camera_logic_utility", "frame_sequence_recorder",
              "lighting_present_utility", "render_pipeline_utility", "rigging_automator", "scene_orchestrator", "src_governor_bridge"]


def run_cgi_diagnostics():
    print("--- Starting Master CGI Silo Diagnostic ---")
    failed = 0
    for op in operations:
        try:
            tool = getattr(importlib.import_module(f"lib.{op}_tool"), f"{op}_tool")
            cfg = getattr(importlib.import_module(f"config.{op}_config"), f"{op}_config")
            instance = tool(cfg)
            methods = [m for m in dir(instance) if not m.startswith("_") and callable(getattr(instance, m))]
            if not methods:
                raise RuntimeError("the tool has no public methods")
            print(f"DIAGNOSTIC: {op} [PASSED - {len(methods)} method(s)]")
        except Exception as e:
            failed += 1
            print(f"DIAGNOSTIC: {op} [FAILED - {type(e).__name__}: {e}]")
    print("--- CGI Diagnostic Complete: %d/%d passed ---" % (len(operations) - failed, len(operations)))
    return failed


if __name__ == "__main__":
    sys.exit(1 if run_cgi_diagnostics() else 0)
