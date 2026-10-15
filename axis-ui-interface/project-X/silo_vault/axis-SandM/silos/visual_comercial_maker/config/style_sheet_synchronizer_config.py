class StyleSheetSynchronizerConfig:
    def __init__(self):
        # Operational parameters for the Style Sheet Synchronizer
        self.SOURCE_TOKEN_PATH = "assets/design_tokens.json"
        self.OUTPUT_PATH = "assets/compiled_styles/"
        
        # Sync preferences
        self.AUTO_APPLY_CHANGES = True
        self.STRICT_BRAND_ENFORCEMENT = True
