# Final Copy: Sovereign Silo Transformation Logic
from src.processor.transform_tool import TransformTool
from src.processor.transform_config import TransformConfig

class Transform:
    def __init__(self, processor_port):
        self.processor_port = processor_port
        
        # Initialize Triad components
        self.tool = TransformTool(self)
        self.config = TransformConfig()

    def process_packet(self, raw_data):
        """
        Transforms raw validated data into internal Silo-specific format.
        """
        transformed = self.tool.apply_schema(raw_data)
        self.processor_port.audit.record_event("TRANSFORM_SUCCESS", "SILO_CORE", "Data converted.")
        return transformed