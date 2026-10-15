import sys
import os

# Set up the path to the root folder
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import your governor utilities
from src.governor.governor_flow_control_utility import governorflowcontrolutility
from src.governor.governor_handshake_utility import governorhandshakeutility
from src.governor.governor_override_utility import governoroverrideutility
from src.governor.governor_pulse_utility import governorpulseutility
from src.governor.governor_sync_utility import governorsyncutility

def run_diagnostics():
    print("--- Starting Governor System Diagnostics ---")
    
    # Initialize your governor utilities here
    # Example:
    # flow = governorflowcontrolutility()
    # print("Governor Flow Control Initialized")
    
    print("--- All Governor Systems Ready ---")

if __name__ == "__main__":
    run_diagnostics()