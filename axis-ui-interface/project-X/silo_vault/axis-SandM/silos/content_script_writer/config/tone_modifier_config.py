class ToneModifierConfig:
    def __init__(self):
        # Operational parameters for the Tone Modifier
        self.DEFAULT_PERSONA = "THOUGHT_LEADER"
        self.ALLOW_EMOTIVE_SHIFT = False
        
        # Available styles
        self.SUPPORTED_STYLES = ["ACADEMIC", "CASUAL", "URGENT", "PERSUASIVE"]
