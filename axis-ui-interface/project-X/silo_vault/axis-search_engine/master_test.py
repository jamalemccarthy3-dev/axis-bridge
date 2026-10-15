"""master_test.py - verifies axis-search_engine from its own files. Offline by default (the search itself needs the internet): python master_test.py [--live]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bridge_diagnostic import deck
from config.master_config import MasterConfig


def run_search_engine_verification(live=False):
    print("--- Starting Verification Sweep: AXIS_SEARCH_ENGINE ---")
    master = MasterConfig()
    problems = master.run_diagnostic_handshake()
    for name, st in master.status.items():
        deck.report_status("AXIS_SEARCH_ENGINE", name, {"status": st})
    deck.report_status("AXIS_SEARCH_ENGINE", "SYSTEM", "ALL_COMPONENTS_LOADED" if not problems else "INCOMPLETE: %d component(s)" % problems)
    if live:
        from search_engine import search_web
        print("[*] Live search for 'stocks':")
        print(search_web("stocks"))
    print("\n%s" % ("OK: every component loads." if not problems else "%d component(s) failed to load." % problems))
    return problems


if __name__ == "__main__":
    sys.exit(1 if run_search_engine_verification("--live" in sys.argv) else 0)
