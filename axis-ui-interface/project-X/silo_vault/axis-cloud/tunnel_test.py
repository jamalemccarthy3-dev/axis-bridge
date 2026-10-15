#!/usr/bin/env python3
"""
tunnel_test.py
Live connection persistence and stability test script for the AXIS tunnel bridge.
Maintains a continuous heartbeat stream to verify connection integrity under load.
"""

import time
import requests
import sys

TARGET_URL = "http://127.0.0.1:5000/api/status"
DURATION_SECONDS = 15
INTERVAL_SECONDS = 1

def run_persistence_test():
    print(f"[AXIS-TEST] Initiating connection persistence test against {TARGET_URL}")
    print(f"[AXIS-TEST] Target window: {DURATION_SECONDS} seconds with {INTERVAL_SECONDS}s heartbeat interval.\n")
    
    start_time = time.time()
    successful_beats = 0
    failed_beats = 0
    latencies = []

    try:
        while time.time() - start_time < DURATION_SECONDS:
            beat_start = time.time()
            try:
                response = requests.get(TARGET_URL, timeout=2)
                latency = (time.time() - beat_start) * 1000
                latencies.append(latency)
                
                if response.status_code == 200:
                    successful_beats += 1
                    print(f"  [HOLD-OK] Heartbeat acknowledged | Latency: {latency:.2f}ms | Status: {response.status_code}")
                else:
                    failed_beats += 1
                    print(f"  [HOLD-WARN] Heartbeat responded with non-200 code: {response.status_code}")
            except requests.exceptions.RequestException as e:
                failed_beats += 1
                print(f"  [HOLD-FAIL] Connection dropped or unreachable: {e}")
            
            time.sleep(INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\n[AXIS-TEST] Persistence test interrupted by operator.")

    print("\n--- Persistence Test Report ---")
    print(f"Total Successful Beats: {successful_beats}")
    print(f"Total Failed Beats:     {failed_beats}")
    if latencies:
        print(f"Average Latency:        {sum(latencies) / len(latencies):.2f}ms")
    total_beats = successful_beats + failed_beats
    stability = (successful_beats / total_beats) * 100 if total_beats > 0 else 0.0
    print(f"Connection Stability:   {stability:.1f}%")

if __name__ == "__main__":
    run_persistence_test()