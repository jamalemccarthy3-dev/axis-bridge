from lib.logger_tool import loggertool
from lib.event_bus import eventbus
from lib.secure_validator import securevalidator

class DistributerAgent:
    def __init__(self):
        self.logger = loggertool.get_logger("DISTRIBUTER_AGENT")
        self.bus = eventbus()
        self.validator = securevalidator()

    def start(self):
        self.logger.info("Distributer Agent online.")
