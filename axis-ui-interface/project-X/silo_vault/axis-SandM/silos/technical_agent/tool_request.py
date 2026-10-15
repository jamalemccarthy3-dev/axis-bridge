from lib.logger_tool import loggertool
from lib.event_bus import eventbus
from lib.telemetry_metrics_tool import telemetrytool

class TechnicalAgent:
    def __init__(self):
        self.logger = loggertool.get_logger("TECHNICAL_AGENT")
        self.bus = eventbus()
        self.telemetry = telemetrytool(self.logger)

    def start(self):
        self.logger.info("Technical Agent online.")
