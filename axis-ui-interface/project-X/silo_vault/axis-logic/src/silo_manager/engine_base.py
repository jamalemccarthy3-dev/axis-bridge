# MASTER ENGINE BRIDGE: SRC/engine_base.py
import os

_ENGINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REQUIRED = ("engine_base.py", "risk.py", "signal.py")             # what a silo folder must hold to be a silo


class EngineBase:
    """The master bridge every silo builds on. A silo is a folder of this engine named after it (ECOM -> ecom/) that holds the required modules; handshake() and check_status() look at
    the folder for real, so an unknown or half-built silo is refused instead of being told 'ready'."""

    def __init__(self, silo_name):
        self.silo_name = silo_name

    def _missing(self):
        folder = os.path.join(_ENGINE, str(self.silo_name).lower())
        if not os.path.isdir(folder):
            return ["the silo folder %s" % os.path.basename(folder)]
        return [f for f in REQUIRED if not os.path.isfile(os.path.join(folder, f))]

    def handshake(self):
        """Enforces the protocol: only a silo that exists on disk is let in. -> 'ACCESS_GRANTED_TO_<name>' or 'ACCESS_DENIED_TO_<name>'."""
        return ("ACCESS_DENIED_TO_%s" if self._missing() else "ACCESS_GRANTED_TO_%s") % self.silo_name

    def check_status(self):
        """'READY' when the silo folder holds every required module, else 'NOT_READY: missing ...'."""
        missing = self._missing()
        return "READY" if not missing else "NOT_READY: missing " + ", ".join(missing)


# This acts as the factory for child engines: this one definition powers the whole fleet
def create_bridge(silo_name):
    return EngineBase(silo_name)
