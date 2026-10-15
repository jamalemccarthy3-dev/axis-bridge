# src/hypothesis_engine/hypothesis_engine_config.py

class HypothesisEngineConfig:
    """
    Configuration for hypothesis_engine.
    Defines parameters for remote automated testing and heuristic analysis.
    """
    def __init__(self):
        self.test_api_endpoint = "https://testing.sovereign-shift.net/v1/analyze"
        self.default_iterations = 100
        self.timeout = 60.0