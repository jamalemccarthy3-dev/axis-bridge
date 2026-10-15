
class NarrativeEngineConfig:
    def __init__(self):
        # Operational parameters for the Narrative Engine
        self.PREFERRED_ARC_TYPES = ["PROBLEM_SOLUTION", "DATA_DRIVEN_STORY", "THOUGHT_LEADERSHIP"]
        self.LENGTH_CONSTRAINT_WORDS = 1500
        
        # Narrative settings
        self.ENFORCE_STORY_BEATS = True
        self.DEFAULT_PACING = "FAST"
