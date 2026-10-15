# Final Copy: Sovereign Silo Computation Logic
from src.processor.computer_tool import ComputerTool
from src.processor.computer_config import ComputerConfig

class Computer:
    def __init__(self, processor_port):
        self.processor_port = processor_port
        
        # Initialize Triad components
        self.tool = ComputerTool(self)
        self.config = ComputerConfig()

    def run_calculation(self, transformed_data):
        """
        Executes the primary logic cycle for the silo.
        Computes outputs based on transformed internal data.
        """
        result = self.tool.execute_logic(transformed_data)
        self.processor_port.audit.record_event("COMPUTATION_SUCCESS", "SILO_CORE", "Logic cycle complete.")
        return result
