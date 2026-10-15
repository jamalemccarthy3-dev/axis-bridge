"""master_test.py - verifies axis-video_creator from the files on disk (see health_report.py). Exit code 0 only when all is well."""
import sys

from bridge_diagnostic import deck
import health_report
from config.master_config import SILO_REGISTRY

ENGINE_ID = "AXIS_VIDEO_CREATOR"


def initialize_engine():
    print(f"--- Verifying {ENGINE_ID} (files on disk) ---")
    problems = 0
    for name, rel in SILO_REGISTRY.items():
        res = health_report.check(name, rel)
        broken = {k: v for k, v in res.items() if v[0] in ("MISSING", "IMPORT_ERROR", "PROBE_FAILED")}
        status = "READY" if not broken else "BROKEN (%d)" % len(broken)
        problems += len(broken)
        deck.report_status(ENGINE_ID, name, {"status": status, "modules": len(res), "broken": sorted(broken)})
        print(f"Silo: {name} | Status: {status}")
    deck.report_status(ENGINE_ID, "SYSTEM", "ALL_SILOS_IMPORT" if not problems else "INCOMPLETE: %d issue(s)" % problems)
    return problems


if __name__ == "__main__":
    sys.exit(1 if initialize_engine() else 0)
