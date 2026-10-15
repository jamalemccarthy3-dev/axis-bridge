# silos/sports.py - the sports engine: estimates with their uncertainty, never a bet.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "src", "silo_manager")):
    if _p not in sys.path:
        sys.path.append(_p)

import markets  # noqa: E402
import pipeline  # noqa: E402


class SportsEngine:
    def __init__(self):
        self.name = "Sports Engine"
        self.pipeline = pipeline.for_silo(_HERE)

    def calculate(self, data):
        """data: {"wins": int, "games": int, "decimal_odds": [odds of every outcome], "outcome_index": which outcome is being considered}.
        The evidence is the record (wins of games); the odds say what the market implies. A BET needs the pipeline's gates AND a positive edge
        measured with the LOWER bound of the probability. -> a decision record (nothing is staked)."""
        record = {"successes": data["wins"], "trials": data["games"]}
        for key in ("drift", "volatility", "direction"):
            if key in data:
                record[key] = data[key]
        decision = self.pipeline.run(record)
        implied, overround = markets.implied_probabilities(data["decimal_odds"])
        i = int(data.get("outcome_index", 0))
        e = markets.edge(decision["probability"]["low"], implied[i])
        decision["market"] = {"implied_probability": float(implied[i]), "overround": overround, "edge_using_lower_bound": e}
        if decision["action"] == self.pipeline.strategy.rules.get("action_high") and e <= 0:
            decision["action"] = self.pipeline.low_action
            decision["vetoed"] = True
            decision["reasons"].append("no edge: the odds already imply %.3f and the conservative estimate is %.3f" % (implied[i], decision["probability"]["low"]))
        decision["suggested_stake_fraction"] = markets.kelly_fraction(decision["probability"]["low"], data["decimal_odds"][i]) if decision["action"] != self.pipeline.low_action else 0.0
        decision["engine"] = self.name
        return decision
