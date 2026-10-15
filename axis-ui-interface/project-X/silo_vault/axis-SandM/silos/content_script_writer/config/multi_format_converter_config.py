class MultiFormatConverterConfig:
    def __init__(self):
        # Operational parameters for the Multi-Format Converter
        self.SUPPORTED_FORMATS = ["VIDEO_STORYBOARD", "SOCIAL_THREAD", "TECHNICAL_DOC"]
        
        # Transcoding settings
        self.PRESERVE_BRAND_VOICE = True
        self.AUTO_FORMAT_SCALING = True
