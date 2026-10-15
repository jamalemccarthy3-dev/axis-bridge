# silos/ecom.py - the e-commerce engine: conversion rates and A/B tests with their uncertainty, never an automatic change.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "src", "silo_manager")):
    if _p not in sys.path:
        sys.path.append(_p)

import markets  # noqa: E402
import pipeline  # noqa: E402
import math  # noqa: E402


class EcomEngine:
    def __init__(self):
        self.name = "Ecom Engine"
        self.pipeline = pipeline.for_silo(_HERE)

    def calculate(self, data):
        """data: {"control": {"visitors", "orders"}, "variant": {"visitors", "orders"}}. The signal is the probability that the variant really beats
        the control (normal approximation of the two-proportion test). Too little traffic gives a probability near 0.5, so the engine says HOLD.
        -> a decision record (nothing on the site is changed)."""
        c, v = data["control"], data["variant"]
        test = markets.ab_test(c["orders"], c["visitors"], v["orders"], v["visitors"])
        p_better = 0.5 * math.erfc(-test["z"] / math.sqrt(2.0))                  # P(variant better), from z
        significant = test["significant"]
        # a lift that is not statistically significant is treated as a coin flip, whatever the z-score says
        decision = self.pipeline.run({"probability": p_better if significant else min(p_better, 0.5), **{k: data[k] for k in ("drift",) if k in data}})
        if not significant:
            decision["reasons"].append("not statistically significant (p = %.2f): more traffic is needed before changing anything" % test["p_value"])
            if decision["action"] != self.pipeline.low_action:
                decision["action"], decision["vetoed"] = self.pipeline.low_action, True
        decision["ab_test"] = dict(test, probability_variant_better=p_better, control=markets.conversion_signal(c["visitors"], c["orders"]),
                                   variant=markets.conversion_signal(v["visitors"], v["orders"]))
        decision["engine"] = self.name
        return decision
