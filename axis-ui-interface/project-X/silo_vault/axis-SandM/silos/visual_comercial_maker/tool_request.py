from lib.logger_tool import loggertool
from lib.event_bus import eventbus

class VisualComercialMakerAgent:
    def __init__(self):
        self.logger = loggertool.get_logger("VISUAL_MAKER")
        self.bus = eventbus()

    def start(self):
        self.logger.info("Visual Commercial Maker online.")
