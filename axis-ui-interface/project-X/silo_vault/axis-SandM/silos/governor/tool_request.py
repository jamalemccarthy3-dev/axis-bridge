import os

from lib.logger_tool import loggertool
from lib.event_bus import eventbus
from config.master_config import MasterConfig


class GovernorAgent:
    """Starts first. Checks that every governor utility the registry lists really exists in src/governor."""

    def __init__(self):
        self.logger = loggertool.get_logger("GOVERNOR")
        self.bus = eventbus()
        self.config = MasterConfig()

    def missing_utilities(self):
        spec = self.config.silos["governor"]
        folder = os.path.join(self.config.root_path, spec["path"])
        return [u for u in spec["utilities"] if not os.path.isfile(os.path.join(folder, u))]

    def start(self):
        missing = self.missing_utilities()
        if missing:
            self.logger.error("Governor online but missing: " + ", ".join(missing))
        else:
            self.logger.info("Governor online. All %d governor utilities present." % len(self.config.silos["governor"]["utilities"]))
        return not missing

    def link(self):
        """This engine's signed door to NEXXUS (orders arrive and builds are reported through the governor only)."""
        from nexxus_link import client
        return client()
