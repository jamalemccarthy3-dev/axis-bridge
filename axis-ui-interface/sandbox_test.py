# Updated Test Script: sandbox_test.py (Direct Browser Target)
import sys
import os
import webbrowser

# Add the config folder to the path so python can locate config_master
sys.path.append(os.path.abspath("config"))

from config_master import Config
import importlib.util

# Initialize the sovereign master configuration
config = Config()

# Retrieve the paths and states
sandbox_path = config.get_parameter("sandbox_config_path")
babylon_path = config.get_parameter("babylon_sandbox_path")
active_silos = config.get_parameter("active_silos")

# Adjust path relative to current working directory if stored with a "root/" prefix
if sandbox_path.startswith("root/"):
    sandbox_path = sandbox_path.replace("root/", "", 1)

print(f"[VERIFICATION] Sandbox Config Path: {sandbox_path}")
print(f"[VERIFICATION] Babylon Frontend Path: {babylon_path}")
print(f"[VERIFICATION] Active Silos State: {active_silos}")

# Load and execute the sandbox_config module dynamically
spec = importlib.util.spec_from_file_location("sandbox_config", sandbox_path)
sandbox_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sandbox_module)

print(f"[{sandbox_module.SYSTEM_CORE}] Bridge Initialized Successfully!")
print(f"Theme Loaded: {sandbox_module.UI_THEME['background']}")

# Verify and open Babylon interface directly through browser module
if os.path.exists(babylon_path):
    print(f"[{sandbox_module.SYSTEM_CORE}] Babylon frontend script verified at: {babylon_path}")
    print(f"[{sandbox_module.SYSTEM_CORE}] Launching browser interface...")
    abs_path = os.path.abspath(babylon_path)
    webbrowser.open_new_tab(f"file:///{abs_path}")
else:
    print(f"[WARNING] Babylon script target not found at: {babylon_path}")