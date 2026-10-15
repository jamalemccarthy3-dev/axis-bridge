#
# lib/freeze_all.py
import os
import sys

from lib.auditor import Auditor
from lib.purge_engine import PurgeEngine

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.isfile(os.path.join(_d, "integrity_store.py")):
    _d = os.path.dirname(_d)
if _d not in sys.path:
    sys.path.append(_d)
import integrity_store as store  # noqa: E402


class FailSafe:
    """Fail-Safe Engine (freeze_all.py): the engine's emergency stop for ITS OWN layers. It records the freeze, wipes the bridge buffers, and sets the halt flag
    (data/halt.json) that the shield and bridge consult - from then on no packet passes. It does NOT reboot anything: restarting a machine or stopping other engines is
    not a decision one engine's fail-safe may make, so that is left to NEXXUS and the person running it (the old version ran `reboot`; that is gone)."""

    def __init__(self):
        self.auditor = Auditor()
        self.purger = PurgeEngine()

    def execute_shutdown(self, reason="fail-safe requested"):
        """-> {"halted": True, "purge": the purge result, "reboot": "not performed", "reason"}. Idempotent."""
        self.auditor.log_event("CRITICAL_FAILSAFE", "Initiating system freeze: %s" % reason)
        store.write_json("halt.json", {"halted": True, "at": store.now(), "reason": reason})
        purge = self.purger.run_sanitization("active_buffer")
        self.auditor.log_event("SYSTEM_HALT", "Layers frozen; buffers wiped (%s). No reboot is performed by this engine." % purge.get("status"))
        return {"halted": True, "purge": purge, "reboot": "not performed", "reason": reason}

    @staticmethod
    def is_halted():
        return bool((store.read_json("halt.json", {}) or {}).get("halted"))

    def lift(self, who):
        """Clears the halt flag. Needs a name, which goes into the ledger. -> True if there was a halt to lift."""
        if not who:
            raise ValueError("lifting the halt needs the name of whoever does it")
        had = self.is_halted()
        store.write_json("halt.json", {"halted": False, "lifted_by": who, "at": store.now()})
        if had:
            self.auditor.log_event("HALT_LIFTED", "by %s" % who)
        return had
