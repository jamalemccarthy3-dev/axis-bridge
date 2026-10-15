# silos/stocks.py - the stocks engine: volatility and direction statistics with their uncertainty, never a trade.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "src", "silo_manager")):
    if _p not in sys.path:
        sys.path.append(_p)

import markets  # noqa: E402
import pipeline  # noqa: E402


class StocksEngine:
    def __init__(self):
        self.name = "Stocks Engine"
        self.pipeline = pipeline.for_silo(_HERE)

    def calculate(self, data):
        """data: {"returns": [daily returns], "prices": [optional price series]}. The evidence is the share of up days; the action needs the pipeline's
        conservative (lower-bound) probability to clear the stocks threshold, so a short history cannot BUY. -> a decision record (nothing is traded)."""
        stats = markets.return_stats(data["returns"])
        decision = self.pipeline.run({"successes": round(stats["p_up"] * stats["n"]), "trials": stats["n"], **{k: data[k] for k in ("drift",) if k in data}})
        decision["stats"] = stats
        if data.get("prices"):
            decision["max_drawdown"] = markets.max_drawdown(data["prices"])
        decision["engine"] = self.name
        return decision
