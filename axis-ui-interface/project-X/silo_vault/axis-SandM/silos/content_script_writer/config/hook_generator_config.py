class HookGeneratorConfig:
    def __init__(self):
        # Operational parameters for the Hook Generator
        self.HOOK_STRATEGIES = ["PAIN_POINT", "CURIOSITY_GAP", "COUNTER_INTUITIVE"]
        self.MAX_HOOK_LENGTH_CHARS = 120
        
        # Optimization settings
        self.ENABLE_AB_TESTING_READY = True
        self.TARGET_RETENTION_INDEX = 0.85
