# src/security/shield.py
import importlib.util
import os

from lib.patrol_radio import PatrolRadio

_HERE = os.path.dirname(os.path.abspath(__file__))


def _tool(name, cls):
    spec = importlib.util.spec_from_file_location("integrity_" + name, os.path.join(_HERE, "lib", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, cls)()


class Shield:
    """The gate every packet passes. A safe one is let through and announced on the radio; an unsafe one is isolated in the mirror box (kept exactly as it arrived) and a
    CRITICAL alert goes out with the reasons."""

    def __init__(self):
        self.radio = PatrolRadio()
        self._shield = _tool("shield_tool", "ShieldTool")
        self._box = _tool("mirror_box_tool", "MirrorBoxTool")
        self.last = None

    def inspect(self, data_packet):
        """True when the packet may pass. The full verdict is in self.last."""
        self.last = self._shield.inspect(data_packet)
        if self.last["safe"]:
            self.radio.broadcast("SECURITY_STATUS", "Packet cleared. Moving to Bridge.")
            return True
        self.radio.broadcast("SECURITY_CRITICAL", "Packet refused: %s" % "; ".join(self.last["reasons"]))
        self.last["isolated"] = self.quarantine(data_packet, "; ".join(self.last["reasons"]))
        return False

    def is_safe(self, packet):
        return self._shield.execute_inspection(packet)

    def quarantine(self, packet, reason=""):
        """Moves the packet into the mirror box. -> its record (id, path, sha256)."""
        return self._box.commit_to_storage(packet, reason)
