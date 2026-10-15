class AssetOptimizerConfig:
    def __init__(self):
        # Operational parameters for the Asset Optimizer
        self.INPUT_DIR = "assets/raw/"
        self.OUTPUT_DIR = "assets/optimized/"
        
        # Optimization settings
        self.COMPRESSION_LEVEL = 75 # Percentage of original quality
        self.ALLOW_FORMAT_CONVERSION = True
        self.SUPPORTED_FORMATS = ["png", "jpg", "mp4", "webp"]
