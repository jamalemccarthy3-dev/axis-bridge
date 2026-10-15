#!/usr/bin/env python3
import time
import logging
import os
import sys

# Configure the log: everything gets saved to 'system_audit.log' in the root
logging.basicConfig(
    filename='system_audit.log', 
    level=logging.INFO, 
    format='%(asctime)s - %(message)s'
)

# Registry includes your architectural silos and the operations layer for Omni
silo_registry = ["governor", "worker", "engine_base", "strategy", "operations"]

def watch_over_everyone():
    """
    Cycles through the registry to provide a heartbeat for all silos,
    ensuring the conversation layer (operations) is monitored for Omni.
    The heartbeat (sleep) occurs after the full cycle to maintain
    data freshness.
    """
    while True:
        for silo in silo_registry:
            message = f"Checking {silo}..."
            print(f"[Watchdog]: {message}")
            logging.info(message)
            
        # The system pulses every 30 seconds after a full registry sweep
        time.sleep(30)

if __name__ == "__main__":
    try:
        print("[Watchdog]: System started. Monitoring silos...")
        watch_over_everyone()
    except KeyboardInterrupt:
        print("\n[Watchdog]: System shutdown initiated.")