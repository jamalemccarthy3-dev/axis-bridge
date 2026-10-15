# src/security/mirror.py
import importlib.util
import os

from lib.auditor import Auditor

_HERE = os.path.dirname(os.path.abspath(__file__))


class Mirror:
    """Defensive staging area for isolated data: the packet is kept byte-for-byte in the mirror box store and the isolation is written to the audit ledger with its hash."""

    def __init__(self):
        self.auditor = Auditor()
        spec = importlib.util.spec_from_file_location("integrity_mirror_tool", os.path.join(_HERE, "lib", "mirror_box_tool.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.box = mod.MirrorBoxTool()

    def isolate_packet(self, data_packet, reason=""):
        """-> the storage record (a dict: truthy). The audit entry carries the packet hash, so the ledger and the box can be cross-checked."""
        rec = self.box.commit_to_storage(data_packet, reason)
        self.auditor.log_event("ISOLATION", "Packet %s isolated (%d bytes)%s." % (rec["sha256"][:16], rec["bytes"], "; already stored" if rec["already_there"] else ""))
        return rec
