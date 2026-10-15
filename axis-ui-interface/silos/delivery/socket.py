# Final Copy: Sovereign Data Socket Logic
from src.processor.socket_tool import SocketTool
from src.processor.socket_config import SocketConfig

class Socket:
    def __init__(self, processor_port):
        self.processor_port = processor_port
        
        # Initialize Triad components
        self.tool = SocketTool(self)
        self.config = SocketConfig()

    def transmit_packet(self, data):
        """Routes data through the active socket connection."""
        success = self.tool.send(data)
        if success:
            self.processor_port.audit.record_event("SOCKET_TX", "SILO_CORE", "Transmission successful.")
        return success
