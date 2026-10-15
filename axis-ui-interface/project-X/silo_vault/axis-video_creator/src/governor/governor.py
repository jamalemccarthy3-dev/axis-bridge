# src/governor/governor.py  (the class keeps its original spelling, "Govenor": other silos import it by that name)
import os
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.isfile(os.path.join(_d, "vc_store.py")):
    _d = os.path.dirname(_d)
if _d not in sys.path:
    sys.path.append(_d)
import vc_store as store  # noqa: E402


class Govenor:
    """The engine's authority. Silos send it day reports; it checks them, runs them through the regulator, and records them in the tamper-evident compliance log."""

    def __init__(self):
        self.status = "ACTIVE"

    @staticmethod
    def known_silos():
        cfg = store.load_module("config/master_config.py")
        return set(cfg.SILO_REGISTRY) | {"cgi"} | {p.rsplit("/", 1)[-1] for p in cfg.SILO_REGISTRY.values()}

    def handle_day_report(self, silo_name, report_data):
        """Accepts a report {"status": text, ...} from a known silo. Refused (and logged) if the silo is unknown, the report is not an object with a status, or the
        regulator finds a violation. -> {"status": "SUCCESS", "message", "report_id"} or {"status": "REJECTED", "reasons"}."""
        reasons = []
        if silo_name not in self.known_silos():
            reasons.append("unknown silo %r" % (silo_name,))
        if not isinstance(report_data, dict) or not isinstance(report_data.get("status"), str):
            reasons.append("a report is an object with a text status")
        if not reasons:
            reg = store.load_module("src/governor/lib/regulator_tool.py").verify_regulatory_alignment(report_data, "sovereign_stronghold_v1")
            reasons += reg["violations"]
        tracker = store.load_module("src/governor/lib/tracker_tool.py")
        if reasons:
            tracker.log_compliance_event("DAY_REPORT_REJECTED", silo_name, "; ".join(reasons)[:200], "logs/governance_audit.log")
            return {"status": "REJECTED", "reasons": reasons}
        rid = store.sha256_obj([silo_name, report_data, store.now()])[:12]
        store.append_jsonl("data/day_reports.jsonl", {"id": rid, "silo": silo_name, "at": store.now(), "report": report_data})
        tracker.log_compliance_event("DAY_REPORT", silo_name, report_data["status"], "logs/governance_audit.log")
        return {"status": "SUCCESS", "message": "Report logged by Govenor.", "report_id": rid}
