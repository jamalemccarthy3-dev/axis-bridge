#!/usr/bin/env python3
"""
test_pipeline.py
Executes a full integration pipeline smoke test across the AXIS infrastructure:
tests vault indexing, audit logging, hardware pulse telemetry, and spins up 
the local server on port 5000 to verify live endpoint connections.
"""

import subprocess
import time
import urllib.request
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

def run_pipeline_test():
    print("[TEST-PIPELINE] Starting end-to-end sovereign pipeline test...")
    errors = 0

    # 1. Test Vault Core Module
    print("[TEST-PIPELINE] Testing AxisVaultCore entity indexing...")
    try:
        from axis_vault_core import AxisVaultCore
        vault = AxisVaultCore()
        entity = vault.add_entity("Test-Node-Alpha", "TestEntity", {"status": "verifying"})
        results = vault.query_entities("Test-Node-Alpha")
        if results and any(e["name"] == "Test-Node-Alpha" for e in results):
            print("  [PASS] Vault entity successfully indexed and queried.")
        else:
            print("  [FAIL] Vault entity could not be retrieved.")
            errors += 1
    except Exception as e:
        print(f"  [FAIL] Vault core test raised exception: {e}")
        errors += 1

    # 2. Test Audit Manager Module
    print("[TEST-PIPELINE] Testing AxisAuditMgr logging...")
    try:
        from axis_audit_mgr import AxisAuditMgr
        audit = AxisAuditMgr()
        res = audit.log_event("PIPELINE_TEST", "Executing automated test suite", "INFO")
        if res.get("success"):
            print("  [PASS] Audit log entry written successfully.")
        else:
            print("  [FAIL] Audit manager failed to write log.")
            errors += 1
    except Exception as e:
        print(f"  [FAIL] Audit manager test raised exception: {e}")
        errors += 1

    # 3. Test Hardware Pulse Telemetry
    print("[TEST-PIPELINE] Testing AxisPulse telemetry retrieval...")
    try:
        from axis_pulse import AxisPulse
        pulse = AxisPulse()
        telemetry = pulse.get_system_telemetry()
        if "disk" in telemetry and "load_average" in telemetry:
            print(f"  [PASS] Pulse telemetry gathered successfully: Disk Free {telemetry['disk'].get('percent_free')}%")
        else:
            print("  [FAIL] Pulse telemetry payload incomplete.")
            errors += 1
    except Exception as e:
        print(f"  [FAIL] Pulse test raised exception: {e}")
        errors += 1

    # 4. Test Live Cloud Server Connection (Port 5000)
    print("[TEST-PIPELINE] Spawning AxisCloudServer on port 5000 for connection test...")
    server_script = BASE_DIR / "axis_cloud_server.py"
    server_process = subprocess.Popen([sys.executable, str(server_script)])
    
    # Allow server time to bind and initialize socket
    time.sleep(2)

    try:
        url = "http://127.0.0.1:5000/api/status"
        print(f"[TEST-PIPELINE] Querying endpoint: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "AxisPipelineTest"})
        
        with urllib.request.urlopen(req, timeout=5) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            data = json.loads(body)
            
            if status_code == 200 and data.get("status") == "online":
                print(f"  [PASS] Live connection established. Server status response: {data}")
            else:
                print(f"  [FAIL] Unexpected server response code {status_code} or payload: {body}")
                errors += 1
    except Exception as e:
        print(f"  [FAIL] Failed to connect to local server on port 5000: {e}")
        errors += 1
    finally:
        print("[TEST-PIPELINE] Terminating test server instance...")
        server_process.terminate()
        server_process.wait()

    print("\n--------------------------------------------------")
    if errors == 0:
        print("[TEST-PIPELINE] SUCCESS: End-to-end pipeline and connection tests passed.")
        sys.exit(0)
    else:
        print(f"[TEST-PIPELINE] FAILURE: {errors} pipeline test anomalies detected.")
        sys.exit(1)

if __name__ == "__main__":
    run_pipeline_test()