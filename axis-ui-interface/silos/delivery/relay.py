# Final Copy: Sovereign Data Relay Logic
from src.processor.relay_tool import RelayTool
from src.processor.relay_config import RelayConfig

class Relay:
    def __init__(self, processor_port):
        self.processor_port = processor_port
        
        # Initialize Triad components
        self.tool = RelayTool(self)
        self.config = RelayConfig()

    def route_packet(self, data, target_node):
        """
        Determines the destination and routes the packet 
        according to the sovereign routing table.
        """
        success = self.tool.execute_route(data, target_node)
        self.processor_port.audit.record_event("RELAY_ROUTE", target_node, "Packet distributed.")
        return success
