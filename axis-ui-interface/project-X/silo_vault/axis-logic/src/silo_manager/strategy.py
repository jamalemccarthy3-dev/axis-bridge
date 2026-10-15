# MASTER STRATEGY ENGINE: SRC/strategy.py
class StrategyEngine:
    def __init__(self, silo_name, rules):
        self.silo_name = silo_name
        self.rules = rules

    def run(self, data):
        # The 'Brain' logic: Universal for all Silos
        if data >= self.rules.get('threshold'):
            return self.rules.get('action_high')
        return self.rules.get('action_low')