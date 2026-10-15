from lib.logger_tool import loggertool
from lib.event_bus import eventbus

class AnalystAgent:
    def __init__(self):
        self.logger = loggertool.get_logger("ANALYST")
        self.bus = eventbus()

    def start(self):
        self.logger.info("Analyst Agent online.")
