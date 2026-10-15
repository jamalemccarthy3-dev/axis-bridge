import os
import sys

# Ensure the current directory is in the path
sys.path.append(os.getcwd())

# Directly import the tools from their correct locations
try:
    from lib.logger_tool import loggertool
    from lib.event_bus_tool import eventbus
    from lib.telemetry_metrics_tool import telemetrytool
    from lib.security_validator import securityvalidator
    from lib.config_loader import configloader
    
    # master_config is in the config folder
    from config.master_config import MasterConfig
    
    print("SUCCESS: All tools and configurations imported successfully.")
    
except ImportError as e:
    print(f"FAILED to import tools: {e}")
except Exception as e:
    print(f"An error occurred during boot: {e}")

