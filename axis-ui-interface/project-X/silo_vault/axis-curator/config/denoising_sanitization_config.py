# src/denoising_sanitization_config.py
class DenoisingSanitizationConfig:
    def __init__(self):
        # Configuration for noise filtering patterns
        self.strip_html = True
        self.max_length = 8192  # Enforces a strict buffer size on incoming streams
        self.log_level = "INFO"
        self.sensitivity = 0.5       # how aggressively interference is removed (0 to 1)
        self.noise_threshold = 0.1   # share of a stream that may be noise before it is flagged unclear
