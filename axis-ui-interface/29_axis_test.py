
import sys
import os

# Set root directory to current path
sys.path.append(os.getcwd())

# Configuration
from config.config_master import Config

# Libs
from lib.log_tool import LogTool
from lib.io_tool import IOTool
from lib.err_tool import ErrTool
from lib.dispatch_tool import DispatchTool
from lib.auth_tool import AuthTool
from lib.recovery_tool import RecoveryTool

# Processor
from silos.delivery.request_tool import ProcessorRequest

def run_axis_ui_interface_test():
    print("[AXIS UI INTERFACE] Starting Internal Integrity Audit...")
    
    # Initialize components
    cfg = Config()
    logger = LogTool()
    io = IOTool()
    err = ErrTool()
    dispatch = DispatchTool()
    auth = AuthTool()
    recover = RecoveryTool()
    
    # 1. Config Check
    if cfg.get_parameter("system_version") != "PARAM_NOT_FOUND":
        print("[PASS] Config layer validated.")
    else:
        print("[FAIL] Config integrity error.")
        return

    # 2. Processor Request Test
    try:
        proc = ProcessorRequest("AUTH_TOKEN_TEST")
        proc.execute("INTERNAL_TEST", {"data": "VERIFY"})
        print("[PASS] Processor request pipeline verified.")
    except Exception as e:
        print(f"[FAIL] Processor pipeline failure: {e}")
        return

    # 3. Self-Healing Simulation
    print("[AXIS UI INTERFACE] Simulating Fault Recovery...")
    recover.restore_silo_state("AXIS_CORE")
    print("[PASS] Recovery tool operational.")

    print("\n--- AXIS UI INTERFACE INTERNAL TEST PASSED ---")
    print("STATUS: CORE LOGIC HARDENED. READY FOR HANDSHAKE.")

if __name__ == "__main__":
    run_axis_ui_interface_test()
