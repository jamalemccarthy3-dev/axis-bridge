class AestheticsEnforcerConfig:
    def __init__(self):
        # Operational parameters for the Aesthetics Enforcer
        self.STYLE_GUIDE_PATH = "assets/style_guides/master_aesthetic.json"
        self.STRICT_MODE = True
        
        # Thresholds for visual variance
        self.TOLERANCE_LEVEL = 0.05
        self.AUTO_CORRECT = True
