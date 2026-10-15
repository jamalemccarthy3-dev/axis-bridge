from lib.logger_tool import loggertool
from lib.event_bus import eventbus
from lib.master_config import masterconfig

class ContentWriterAgent:
    def __init__(self):
        self.logger = loggertool.get_logger("CONTENT_WRITER")
        self.bus = eventbus()
        self.config = masterconfig()

    def start(self):
        self.logger.info("Content Writer online.")