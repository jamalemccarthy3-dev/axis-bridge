# MASTER SIGNAL ENGINE: SRC/signal.py
class SignalEngine:
    def __init__(self, silo_name, config):
        self.silo_name = silo_name
        self.config = config

    def process(self, data):
        # Universal purification: Removes noise based on the threshold
        volatility = data.get('volatility', 0)
        if volatility >= self.config.get('min_volatility'):
            return "SIGNAL_ACTIVE", data.get('direction')
        return "STAGNANT", None
