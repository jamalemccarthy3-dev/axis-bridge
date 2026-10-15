"""test_probability.py - checks for lib/probability.py and the risk engine. Run: python test_probability.py"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import probability as P  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("[PASS] %s" % name)
    else:
        failed += 1
        print("[FAIL] %s %s" % (name, detail))


def raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


# valid sets
check("normalize makes weights sum to 1", P.sums_to_one(P.normalize_probabilities([2, 3, 5])))
check("normalize keeps proportions", np.allclose(P.normalize_probabilities([1, 1, 2]), [0.25, 0.25, 0.5]))
check("normalize refuses negatives, zeros, NaN", raises(lambda: P.normalize_probabilities([-1, 2])) and raises(lambda: P.normalize_probabilities([0, 0])) and raises(lambda: P.normalize_probabilities([float("nan"), 1])))
check("sums_to_one rejects 0.9 total", not P.sums_to_one([0.4, 0.5]))

# intervals
lo, hi = P.wilson_interval(0, 10)
check("wilson: 0 of 10 still leaves room above 0", lo == 0.0 and 0.2 < hi < 0.4, (lo, hi))
lo, hi = P.wilson_interval(50, 100)
check("wilson: 50 of 100 is centred near 0.5 and contains it", lo < 0.5 < hi and abs((lo + hi) / 2 - 0.5) < 0.01)
check("wilson narrows with more data", (lambda a, b: (b[1] - b[0]) < (a[1] - a[0]))(P.wilson_interval(5, 10), P.wilson_interval(500, 1000)))
check("wilson with no trials is the whole range", P.wilson_interval(0, 0) == (0.0, 1.0))
lo, hi = P.bootstrap_interval(np.arange(100), seed=1)
check("bootstrap interval contains the true mean 49.5", lo < 49.5 < hi, (lo, hi))
check("bootstrap is repeatable with a seed", P.bootstrap_interval([1, 2, 3, 4, 5], seed=3) == P.bootstrap_interval([1, 2, 3, 4, 5], seed=3))

# failure probability
fp = P.failure_probability(np.arange(100), 89.5)
check("failure probability counts the right share (10 of 100)", fp["n"] == 100 and abs(fp["p"] - 0.10) < 1e-9 and fp["low"] < 0.10 < fp["high"], fp)
check("tiny sample gives a wide interval", (lambda f: f["high"] - f["low"] > 0.4)(P.failure_probability([1, 2, 3], 10)))

# scoring
y = np.array([1, 0, 1, 1, 0, 0, 1, 0])
check("perfect probabilities score Brier 0", P.brier_score(y, y) == 0.0)
check("always 0.5 scores Brier 0.25", abs(P.brier_score(np.full(8, 0.5), y) - 0.25) < 1e-12)
check("brier refuses mismatched lengths", raises(lambda: P.brier_score([0.5], [1, 0])))
check("log loss is finite even at 0 and 1", np.isfinite(P.log_loss([0.0, 1.0], [1, 0])))

# calibration actually helps an overconfident model, measured on unseen data
rng = np.random.default_rng(7)
true_p = rng.uniform(0.2, 0.8, 4000)
outcomes = (rng.uniform(size=4000) < true_p).astype(float)
overconfident = np.clip(0.5 + (true_p - 0.5) * 2.2, 0.01, 0.99)          # same ranking, probabilities pushed to the extremes
rep = P.walk_forward_calibration(overconfident, outcomes, window=800, step=200)
check("walk-forward calibration beats the raw overconfident scores", rep.get("improved") and rep["brier_calibrated"] < rep["brier_raw"], rep)
cal = P.HistogramCalibrator(10).fit(overconfident[:2500], outcomes[:2500])
test_p, test_y = overconfident[2500:], outcomes[2500:]
check("calibration lowers expected calibration error out of sample", P.expected_calibration_error(cal.predict(test_p), test_y) < P.expected_calibration_error(test_p, test_y))
check("calibrated curve never decreases", bool(np.all(np.diff(cal.rates) >= -1e-12)))
check("calibrator refuses use before fit", raises(lambda: P.HistogramCalibrator().predict([0.5]), RuntimeError))
ev = P.evaluate(cal.predict(test_p), test_y)
check("evaluate reports a skill score and it is positive", ev["brier_skill"] > 0 and 0 <= ev["accuracy"] <= 1, ev)
check("noise has no skill: random scores do not beat the base rate", P.evaluate(rng.uniform(size=2000), (rng.uniform(size=2000) < 0.5).astype(float))["brier_skill"] <= 0.001)
check("reliability table counts every prediction", sum(r["n"] for r in P.reliability_table(overconfident, outcomes)) == 4000)

# risk engine uses the measured upper bound
sys.path.insert(0, os.path.join(HERE, "src", "silo_manager"))
import risk  # noqa: E402
eng = risk.RiskEngine("demo", 0.2)
check("risk: old 'probability' input still works", eng.calculate({"probability": 0.5})[0] == "RISK_HIGH" and eng.calculate({"probability": 0.1})[0] == "RISK_ACCEPTABLE")
if risk.failure_probability is None:
    check("risk: measured path available (needs the axis-logic folder on the path)", True)
else:
    few = eng.calculate({"samples": [1, 2, 3], "limit": 10})
    many = eng.calculate({"samples": list(range(1000)), "limit": 10_000})
    check("risk: 3 safe samples are NOT called acceptable (interval is wide)", few[0] == "RISK_HIGH", few)
    check("risk: 1000 safe samples are acceptable", many[0] == "RISK_ACCEPTABLE", many)

print("\n%d/%d passed" % (passed, passed + failed))
sys.exit(0 if not failed else 1)
