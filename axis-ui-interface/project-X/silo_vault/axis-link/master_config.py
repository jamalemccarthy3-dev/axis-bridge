import os
from bridge_diagnostic import deck

## 1. DYNAMIC IDENTITY
# No longer hardcoded to a specific engine name, it identifies by current directory
ENGINE_ID = os.path.basename(os.getcwd())

## 2. DYNAMIC DISCOVERY (The "Open" Approach)
def get_silo_registry():
    """Dynamically maps the folder contents instead of hardcoding files."""
    registry = {}
    for item in os.listdir('.'):
        # Ignore hidden files like .git or this script itself
        if item.startswith('.') or item == "master_config.py":
            continue
            
        # If it's a folder, categorize it as a 'sub_silo'; if file, 'asset'
        if os.path.isdir(item):
            registry[item] = "SUB_SILO"
        else:
            registry[item] = "ASSET"
    return registry

def perform_health_assessment(component_name):
    """Standardized verification for dynamic components."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, component_name)
    if not os.path.exists(path):
        return {"status": "MISSING", "last_check": "FILE_CHECK"}
    if os.path.isfile(path) and path.endswith(".py"):
        try:
            compile(open(path, encoding="utf-8", errors="replace").read(), path, "exec")      # a real syntax check
        except SyntaxError as e:
            return {"status": "SYNTAX_ERROR (line %s)" % e.lineno, "last_check": "FILE_CHECK"}
    return {"status": "READY", "last_check": "FILE_CHECK"}

def initialize_engine():
    """Report status to the Bridge Governor using dynamic discovery."""
    print(f"--- Initiating Verification for {ENGINE_ID} ---")
    
    # Get current inventory
    current_registry = get_silo_registry()
    
    for component in current_registry.keys():
        assessment = perform_health_assessment(component)
        # Registering distributed components with the Governor
        deck.report_status(ENGINE_ID, component, assessment)
        print(f"Component: {component} | Status: {assessment['status']}")
        
    deck.report_status(ENGINE_ID, "SYSTEM", "FILES_CHECKED")

if __name__ == "__main__":
    initialize_engine()