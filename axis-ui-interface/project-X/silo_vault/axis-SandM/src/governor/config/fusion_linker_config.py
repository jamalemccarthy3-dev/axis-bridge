class FusionLinkerConfig:
    def __init__(self):
        # Operational parameters for the Fusion Linker
        self.ROOT_FUSION_PATH = "data/config/root_fusion.json"
        self.SYNC_ON_STARTUP = True
        
        # Link settings
        self.OVERRIDE_LOCAL_ON_CONFLICT = False
        self.LOG_SYNC_EVENTS = True
