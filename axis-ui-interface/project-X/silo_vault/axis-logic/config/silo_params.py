# config/silo_params.py
class SiloParams:
    def __init__(self):
        self.SILO_WEIGHTS = {
            "sports": 1.5,
            "stocks": 1.2,
            "econ": 0.8,   # Elevated to provide sharper macro-trend signals
            "logs": 0.9,   # Elevated to ensure logistics throughput visibility
            "risk": 1.2,
            "signal": 1.0,
            "entropy": 0.9,
            "strategy": 1.0,
            "feedback": 1.0
        }

    def get_weights(self):
        return self.SILO_WEIGHTS
