# Final Copy: Sovereign Silo Validation Logic
from src.processor.validate_tool import ValidateTool
from src.processor.validate_config import ValidateConfig

class Validate:
    def __init__(self, processor_port):
        self.processor_port = processor_port
        
        # Initialize Triad components
        self.tool = ValidateTool(self)
        self.config = ValidateConfig()

    def validate_input(self, data_packet):
        """
        Hard-check: Validates that the input packet matches 
        the silo's strict schema.
        """
        if not data_packet:
            return False
            
        # Check against schema constraints
        is_valid = self.tool.check_schema(data_packet)
        if not is_valid:
            self.processor_port.audit.record_event("VALIDATION_FAILURE", "SILO_CORE", "Data schema mismatch.")
            
        return is_valid
