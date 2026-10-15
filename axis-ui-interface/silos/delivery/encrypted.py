# Final Copy: Sovereign Data Encryption Logic
from src.processor.encrypted_tool import EncryptedTool
from src.processor.encrypted_config import EncryptedConfig

class Encrypted:
    def __init__(self, processor_port):
        self.processor_port = processor_port
        
        # Initialize Triad components
        self.tool = EncryptedTool(self)
        self.config = EncryptedConfig()

    def secure_packet(self, formatted_data):
        """
        Encrypts the formatted packet for secure transit.
        """
        encrypted_packet = self.tool.apply_encryption(formatted_data)
        self.processor_port.audit.record_event("ENCRYPT_SUCCESS", "SILO_CORE", "Data hardened.")
        return encrypted_packet
