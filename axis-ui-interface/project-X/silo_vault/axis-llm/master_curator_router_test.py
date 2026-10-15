"""
Real execution tests for CuratorRouter (Phase 14: Core Engine & Utility
Integration). These actually run the pipeline against the real module -
no mocked assertions - including genuinely monkey-patched stage methods,
a genuine crash injected into a stage, and a genuine slow stage observed
from a second thread to prove the heartbeat lifecycle.

Run with: python3 test_curator_router.py
"""
import importlib.util
import sys
import threading
import time
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "nexxus_talks.py"

_checks_run = 0
_checks_passed = 0


def check(label, condition):
    global _checks_run, _checks_passed
    _checks_run += 1
    status = "PASS" if condition else "FAIL"
    if condition:
        _checks_passed += 1
    print(f"[{status}] {label}")
    return condition


def load_module():
    spec = importlib.util.spec_from_file_location("nexxus_talks_under_test", str(MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nexxus_talks_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    mod = load_module()
    CuratorRouter = mod.CuratorRouter
    CURATOR_STAGES = mod.CURATOR_STAGES

    # ---- 1. initial silent-rest state ----
    cr = CuratorRouter()
    check("starts at rest (heartbeat_active is False)", cr.heartbeat_active is False)
    check("no prior run recorded", cr.last_run is None)

    # ---- 2. sequential execution against real fallback stubs (no engine files on disk) ----
    result = cr.run_pipeline({"prompt": "test run, no asset_path"})
    check("all six stages present", set(result["stages"].keys()) == set(CURATOR_STAGES))
    check("render skipped (no asset_path given)", result["stages"]["render"]["status"] == "skipped")
    check("manifest reports unavailable (no real engine)", result["stages"]["manifest"]["status"] == "unavailable")
    check("rotate reports unavailable (no real engine)", result["stages"]["rotate"]["status"] == "unavailable")
    check("dispatch reports unavailable (no real engine)", result["stages"]["dispatch"]["status"] == "unavailable")
    check("sync reports unavailable (no real engine)", result["stages"]["sync"]["status"] == "unavailable")
    check("pulse reports unavailable (no real engine)", result["stages"]["pulse"]["status"] == "unavailable")
    check("overall status is honestly 'partial', not 'success'", result["status"] == "partial")
    check("sealed_at is None when not a genuine full success", result["sealed_at"] is None)
    check("heartbeat reset to False after run", cr.heartbeat_active is False)

    # ---- 3. genuine all-stages-succeed case ----
    cr_all = CuratorRouter()
    for stage in CURATOR_STAGES:
        setattr(cr_all, f"_stage_{stage}", lambda spec, prior: {"status": "success"})
    result_all = cr_all.run_pipeline({"asset_path": "/tmp/fake_asset"})
    check("genuine full success reports overall 'success'", result_all["status"] == "success")
    check("sealed_at is set on genuine success", result_all["sealed_at"] is not None)
    check("heartbeat reset to False after full success", cr_all.heartbeat_active is False)

    # ---- 4. heartbeat lifecycle: observable True during a genuinely slow stage ----
    cr_slow = CuratorRouter()

    def slow_dispatch(spec, prior):
        time.sleep(0.3)
        return {"status": "success"}

    cr_slow._stage_dispatch = slow_dispatch
    observed = {}

    def runner():
        cr_slow.run_pipeline({"prompt": "slow test"})

    t = threading.Thread(target=runner)
    check("heartbeat False before run starts", cr_slow.heartbeat_active is False)
    t.start()
    time.sleep(0.1)
    observed["during"] = cr_slow.heartbeat_active
    t.join()
    observed["after"] = cr_slow.heartbeat_active
    check("heartbeat True while a stage is actually still running", observed["during"] is True)
    check("heartbeat False once run has completed", observed["after"] is False)

    # ---- 5. a stage that raises is contained; later stages still run ----
    cr_crash = CuratorRouter()

    def crashing_manifest(spec, prior):
        raise RuntimeError("simulated engine crash")

    cr_crash._stage_manifest = crashing_manifest
    result_crash = cr_crash.run_pipeline({"prompt": "crash test"})
    check("crashed stage reported as 'error', not propagated", result_crash["stages"]["manifest"]["status"] == "error")
    check("stage after the crash still ran", "pulse" in result_crash["stages"])
    check("overall status still 'partial' (clean dict, not a raised exception)", result_crash["status"] == "partial")
    check("heartbeat still resets to False even after a stage crash", cr_crash.heartbeat_active is False)

    # ---- 6. malformed non-dict input is rejected cleanly ----
    cr_bad = CuratorRouter()
    result_bad = cr_bad.run_pipeline("not a dict")
    check("non-dict package_spec rejected with status 'error'", result_bad["status"] == "error")
    check("heartbeat never set True for rejected input", cr_bad.heartbeat_active is False)

    # ---- 7. chat dispatch wiring ----
    bridge = mod.bridge
    seal_intent = bridge.execute_engine_intent("seal package and run curator now")
    check("'seal package...' routes to CuratorRouter engine", seal_intent is not None and seal_intent["engine"] == "CuratorRouter")
    check("'seal package...' result carries a pipeline status", "status" in seal_intent["result"])

    status_intent = bridge.execute_engine_intent("what's the curator status")
    check("'curator status' routes to CuratorRouter engine", status_intent is not None and status_intent["engine"] == "CuratorRouter")
    check("'curator status' result carries heartbeat_active", "heartbeat_active" in status_intent["result"])

    print(f"\n{_checks_passed}/{_checks_run} checks passed.")
    if _checks_passed != _checks_run:
        sys.exit(1)


if __name__ == "__main__":
    main()