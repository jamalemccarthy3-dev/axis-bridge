import importlib
import os
import sys

# Add the current directory to sys.path to ensure local imports work
sys.path.append(os.getcwd())

# Define modules to test in the root directory
# Added master_interface_utility and orchestrator_utility correctly here
root_modules = [
    "automated_metadata_tagging",
    "checksum_verification",
    "curate_input_path",
    "denoising_sanitization",
    "master_interface_utility",
    "optimize_storage",
    "orchestrator_utility",
    "verify_integrity"
]

# Define modules to test in src/governor
governor_modules = [
    "src.governor.categorization_cataloging_engine",
    "src.governor.dependency_mapper",
    "src.governor.life_cycle_policy"
]

def verify_module(module_name, is_governor=False):
    try:
        # Attempt to import the module
        importlib.import_module(module_name)
        print(f"[PASS] {module_name} initialized successfully.")
        
        # Determine pathing based on whether it is a root or governor module
        if is_governor:
            # Strip the 'src.governor.' prefix to get the filename for lib/config lookups
            base_name = module_name.split('.')[-1]
            tool_path = os.path.join("src", "governor", "lib", f"{base_name}_tool.py")
            config_path = os.path.join("src", "governor", "config", f"{base_name}_config.py")
        else:
            # Root modules use the module_name directly
            tool_path = os.path.join("lib", f"{module_name}_tool.py")
            config_path = os.path.join("config", f"{module_name}_config.py")
        
        # Check for tool file
        if os.path.exists(tool_path):
            print(f"  [CHECK] {tool_path} located.")
        else:
            print(f"  [FAIL] {tool_path} NOT FOUND.")
            
        # Check for config file
        if os.path.exists(config_path):
            print(f"  [CHECK] {config_path} located.")
        else:
            print(f"  [FAIL] {config_path} NOT FOUND.")
            
    except ImportError as e:
        print(f"[FAIL] {module_name} could not be imported. Error: {e}")
    except Exception as e:
        print(f"[FAIL] Unexpected error testing {module_name}: {e}")

def run_master_test():
    print("--- Starting Full Master Test (Root & Governor) ---")
    
    print("\n[Testing Root Modules]")
    for mod in root_modules:
        verify_module(mod, is_governor=False)
        
    print("\n[Testing Governor Modules]")
    for mod in governor_modules:
        verify_module(mod, is_governor=True)

    print("\n--- Master Test Complete ---")

if __name__ == "__main__":
    run_master_test()