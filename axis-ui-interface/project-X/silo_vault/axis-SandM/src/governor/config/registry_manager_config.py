class RegistryManagerConfig:
    def __init__(self):
        # Operational parameters for the Registry Manager
        self.REGISTRY_PATH = "data/master_registry.json"
        self.SCAN_DEPTH = 3
        self.AUTO_RELOAD = True
        
        # Validated silo list for registry cross-reference
        self.TARGET_SILOS = "all"   # every silo in config/master_config.py
