# bridge/live_observer.py
import time
import os
from bridge.bridge_diagnostics import deck

def translate_status(status_data):
    # This keeps your "Plain English" vibe going
    state = status_data.get("state", "unknown")
    if state == "active": return "Everything is running smooth."
    if state == "triage_needed": return "Needs attention—manual override required."
    return f"Current activity: {state}"

def run_live_view():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=== DECK COMMAND CENTER ===")
        
        registry = deck.get_all_reports()
        
        for engine, data in registry.items():
            # 1. The Executive Summary
            print(f"\n[ Engine: {engine.upper()} ]")
            print(f"  Status: {translate_status(data['status'])}")
            
            # 2. The Professional/Tech Detail
            print(f"  Technical Log: {data['status']}")
            print("-" * 30)
        
        time.sleep(3)