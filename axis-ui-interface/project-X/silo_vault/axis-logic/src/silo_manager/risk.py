# MASTER RISK ENGINE: SRC/risk.py
try:
    from lib.probability import failure_probability      # real failure probability with its uncertainty (run from the axis-logic folder)
except ImportError:
    failure_probability = None

class RiskEngine:
    def __init__(self, silo_name, exposure_limit):
        self.silo_name = silo_name
        self.exposure_limit = exposure_limit

    def calculate(self, data):
        # With 'samples' (simulated or historical outcomes) and 'limit', the failure probability is measured, and the decision uses the
        # UPPER end of its interval: a small sample cannot pass as safe. Otherwise a 'probability' you pass in is used as before.
        samples = data.get('samples')
        if samples is not None and data.get('limit') is not None:
            if failure_probability is None:
                raise RuntimeError('lib/probability.py cannot be imported: refusing to fall back to an unmeasured risk (run from the axis-logic folder)')
            est = failure_probability(samples, data['limit'])
            risk_score = est['high']
        else:
            risk_score = data.get('probability', 0)
        if risk_score > self.exposure_limit:
            return "RISK_HIGH", risk_score
        return "RISK_ACCEPTABLE", risk_score
