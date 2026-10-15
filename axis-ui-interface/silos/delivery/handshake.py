import sys
import os

# Ensure Python looks in the current delivery directory
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import the main ProcessorRequest class that already houses all the tools
from request_tool import ProcessorRequest

class Handshake:
    def __init__(self, delivery_port):
        self.delivery_port = delivery_port
        
        # Initialize ProcessorRequest with a dummy token to inherit all tools seamlessly
        self.processor = ProcessorRequest(auth_token="handshake_auth")
        
        # Link the tools directly from the processor
        self.auth = self.processor.auth
        self.dispatch = self.processor.dispatch
        self.logger = self.processor.logger
        
    def initiate_verification(self, target_node):
        """Executes the challenge-response identity check."""
        self.logger.log(f"Initiating handshake with {target_node}")
        
        # Perform identity check via AuthTool
        verified = self.auth.verify(target_node)
        
        if verified:
            self.logger.log("HANDSHAKE_SUCCESS")
            return True
        else:
            self.logger.log("HANDSHAKE_FAILED")
            return False