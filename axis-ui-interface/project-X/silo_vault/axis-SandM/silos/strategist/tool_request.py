from lib.logger_tool import loggertool
from lib.event_bus import eventbus
from lib.master_config import masterconfig

class StrategistAgent:
    def __init__(self):
        self.logger = loggertool.get_logger("STRATEGIST")
        self.bus = eventbus()
        self.config = masterconfig()

    def start(self):
        self.logger.info("Strategist Agent online.")