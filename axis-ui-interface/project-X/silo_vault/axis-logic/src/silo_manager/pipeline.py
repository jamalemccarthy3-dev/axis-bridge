# SRC/silo_manager/pipeline.py - the one pipeline every silo (sports, stocks, ecom, logs) runs its numbers through.
#
#   drift check (entropy) -> activity (signal) -> probability with its interval -> threshold -> risk -> strategy -> decision record
#
# Rules it enforces, so no silo can talk itself into an action:
#   * the strategy and the threshold see the LOWER bound of the probability, never the point estimate (a small sample cannot look confident)
#   * a drifting system (entropy) or a risk above the exposure limit vetoes the action, and the record says why
#   * every decision comes back as a full record: the numbers, each gate's verdict and the reasons
# It recommends; it never acts. Past results do not guarantee future ones.
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))                    # the axis-logic folder
for _p in (ROOT, os.path.join(ROOT, "lib"), HERE):
    if _p not in sys.path:
        sys.path.append(_p)

import probability as P  # noqa: E402


def _load(name):
    """Load a sibling engine by path under a unique name: `signal.py` here must never be confused with Python's own `signal` module."""
    spec = importlib.util.spec_from_file_location("silo_manager_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EntropyEngine = _load("entropy").EntropyEngine
FeedbackEngine = _load("feedback").FeedbackEngine
RiskEngine = _load("risk").RiskEngine
ThresholdManager = _load("threshold").ThresholdManager
StrategyEngine = _load("strategy").StrategyEngine
SignalEngine = _load("signal").SignalEngine

DISCLAIMER = "An estimate with its uncertainty, not advice. Past results do not guarantee future ones."
_PARAM_FILES = (("entropy", "config"), ("signal", "config"), ("risk", "config"), ("thershold", "settings"), ("stratagy", "rules"), ("feedback", "config"))


def load_silo_params(silo_dir):
    """Read a silo's parameter files (<silo>/signal.py defines `config`, thershold.py defines `settings`, stratagy.py defines `rules`, ...).
    They are loaded by path under unique names, so a silo's signal.py can never be confused with Python's own `signal` module."""
    params = {}
    for fname, attr in _PARAM_FILES:
        path = os.path.join(silo_dir, fname + ".py")
        if not os.path.isfile(path):
            continue
        spec = importlib.util.spec_from_file_location("silo_param_%s_%s" % (os.path.basename(silo_dir), fname), path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, attr):
            params[fname] = getattr(mod, attr)
    return params


def for_silo(silo_dir):
    """A pipeline for the silo in `silo_dir`, with that silo's own parameter files."""
    return SiloPipeline(os.path.basename(os.path.abspath(silo_dir)), load_silo_params(silo_dir))


class SiloPipeline:
    def __init__(self, silo_name, params):
        self.silo = silo_name
        rules = params.get("stratagy", {"threshold": 0.5, "action_high": "ACT", "action_low": "HOLD"})
        self.low_action = rules.get("action_low", "HOLD")
        self.entropy = EntropyEngine(silo_name, params.get("entropy", {}).get("drift_tolerance", 0.1))
        self.signal = SignalEngine(silo_name, params.get("signal", {"min_volatility": 0.0}))
        self.threshold = ThresholdManager(silo_name, params.get("thershold", {"threshold_value": 0.5}))
        self.risk = RiskEngine(silo_name, params.get("risk", {}).get("exposure_limit", 0.5))
        self.strategy = StrategyEngine(silo_name, rules)
        self.feedback = FeedbackEngine(silo_name, params.get("feedback", {}).get("learning_rate", 0.1))
        self._history = []                                         # (predicted probability, outcome) pairs for calibration

    # ------------------------------------------------------------------ the decision
    def run(self, obs):
        """obs: successes+trials | probability | (samples+limit), plus optional drift, volatility+direction. -> a decision record."""
        reasons = []
        est = self._estimate(obs)
        conservative = est["low"]
        gates = {}

        state, drift = self.entropy.calculate(obs)
        gates["entropy"] = {"verdict": state, "drift": drift}
        if state != "SYSTEM_STABLE":
            reasons.append("the data is drifting (%.3f above tolerance %.3f): recalibrate before acting" % (drift, self.entropy.drift_tolerance))

        if "volatility" in obs:
            sig, direction = self.signal.process(obs)
            gates["signal"] = {"verdict": sig, "direction": direction}
            if sig != "SIGNAL_ACTIVE":
                reasons.append("the signal is stagnant (volatility %.2f below %.2f)" % (obs["volatility"], self.signal.config.get("min_volatility", 0)))

        ok, msg = self.threshold.validate(conservative)
        gates["threshold"] = {"verdict": "MET" if ok else "NOT_MET", "message": msg, "value_used": conservative}
        if not ok:
            reasons.append("the conservative probability %.3f is under the threshold %.3f" % (conservative, self.threshold.settings.get("threshold_value", 0.5)))

        risk_in = {"samples": obs["samples"], "limit": obs["limit"]} if "samples" in obs and "limit" in obs else {"probability": 1.0 - conservative}
        risk_state, risk_score = self.risk.calculate(risk_in)
        gates["risk"] = {"verdict": risk_state, "score": risk_score, "limit": self.risk.exposure_limit}
        if risk_state != "RISK_ACCEPTABLE":
            reasons.append("risk %.3f is above the exposure limit %.3f" % (risk_score, self.risk.exposure_limit))

        proposed = self.strategy.run(conservative)
        action = proposed if not reasons else self.low_action
        return {"silo": self.silo, "action": action, "proposed_by_strategy": proposed, "vetoed": bool(reasons) and proposed != self.low_action,
                "probability": est, "gates": gates, "reasons": reasons, "disclaimer": DISCLAIMER}

    @staticmethod
    def _estimate(obs):
        if "successes" in obs and "trials" in obs:
            lo, hi = P.wilson_interval(obs["successes"], obs["trials"])
            return {"point": obs["successes"] / obs["trials"], "low": lo, "high": hi, "n": int(obs["trials"]), "interval": "wilson"}
        if "probability" in obs:
            p = float(obs["probability"])
            return {"point": p, "low": p, "high": p, "n": None, "interval": "none (a bare number was supplied: its uncertainty is unknown)"}
        if "samples" in obs and "limit" in obs:
            fp = P.failure_probability(obs["samples"], obs["limit"])
            return {"point": 1.0 - fp["p"], "low": 1.0 - fp["high"], "high": 1.0 - fp["low"], "n": fp["n"], "interval": "wilson (samples above the limit count as failures)"}
        raise ValueError("give successes+trials, a probability, or samples+limit")

    # ------------------------------------------------------------------ learning from outcomes
    def record_outcome(self, predicted_probability, outcome):
        """Remember what was predicted and what happened (1 or 0). Returns the feedback engine's learning step."""
        self._history.append((float(predicted_probability), float(outcome)))
        return self.feedback.calculate({"performance": float(outcome) - float(predicted_probability)})

    def calibration_report(self, bins=5):
        """Is the probability this silo reports honest? Needs recorded outcomes."""
        if len(self._history) < 5:
            return {"n": len(self._history), "note": "not enough recorded outcomes yet (need at least 5)"}
        p, y = zip(*self._history)
        rep = P.evaluate(p, y)
        rep["reliability"] = P.reliability_table(p, y, bins=bins)
        return rep
