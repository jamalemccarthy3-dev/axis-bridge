class PrototypeRendererConfig:
    def __init__(self):
        # Operational parameters for the Prototype Renderer
        self.RENDER_OUTPUT_DIR = "data/render_output/"
        self.RESOLUTION_PRESET = "1920x1080"
        
        # Rendering settings
        self.ENABLE_HARDWARE_ACCELERATION = False   # this renderer writes HTML; it uses no GPU
        self.DEFAULT_FORMAT = "html"   # png and mp4 need a browser / video encoder this engine does not have
