# Final Copy: Sovereign Silo Pipeline Bridge Logic
from src.processor.bridge_tool import BridgeTool
from src.processor.bridge_config import BridgeConfig

class Bridge:
    def __init__(self, processor_port):
        self.processor_port = processor_port
        
        # Initialize Triad components
        self.tool = BridgeTool(self)
        self.config = BridgeConfig()

    def connect_pipeline(self, processor_data, transmission_data):
        """
        Connects the internal silo processing output to the 
        external delivery/socket pipeline.
        """
        connection_status = self.tool.execute_link(processor_data, transmission_data)
        self.processor_port.audit.record_event("BRIDGE_ESTABLISHED", "SILO_CORE", "Pipeline linked.")
        return connection_status
