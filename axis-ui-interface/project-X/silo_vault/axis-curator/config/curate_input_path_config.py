# src/curate_input_path_config.py
import os

class CurateInputConfig:
    def __init__(self):
        # Base operating directory for the Sovereign shift
        self.base_path = os.path.join(os.getcwd(), "data")
        
        # Hard-coded system-level protection for sensitive areas
        self.restricted_paths = [
            os.path.join(os.getcwd(), "src"), # Protect the source code
            os.path.join(os.getcwd(), "config") # Protect the system configuration
        ]