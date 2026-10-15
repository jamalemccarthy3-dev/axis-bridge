# src/security/sentry.py
import importlib.util
import os

from lib.auditor import Auditor
from lib.patrol_radio import PatrolRadio

_HERE = os.path.dirname(os.path.abspath(__file__))


def _sentry_tool():
    spec = importlib.util.spec_from_file_location("integrity_sentry_tool2", os.path.join(_HERE, "lib", "sentry_tool.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SentryTool()


class Sentry:
    """Active threat detection and real-time alert trigger: every packet is compared with the threat database; a match raises an alert naming what matched."""

    def __init__(self):
        self.auditor = Auditor()
        self.patrol = PatrolRadio()
        self._tool = _sentry_tool()
        self.last = None

    def scan_packet(self, data_packet):
        """True when the packet is clean. On a match: a patrol alert (severity of the worst match) and False; the scan result is in self.last."""
        self.last = self._tool.scan(data_packet)
        if not self.last["clean"]:
            self.patrol.broadcast_alert(self.last["worst"], "Threat pattern(s) detected: %s." % ", ".join(t["name"] for t in self.last["threats"]))
            return False
        return True

    def _is_threat(self, data_packet):
        return not self._tool.scan(data_packet)["clean"]
