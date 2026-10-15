"""test_logic_engine.py - axis-logic end to end: the domain math, the shared pipeline's gates, the three silo engines and the data gatekeeper.
Run: python test_logic_engine.py"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("NEXXUS_MESH_URL", "http://127.0.0.1:9")
os.chdir(ROOT)
for p in (os.path.join(ROOT, "lib"), ROOT, os.path.join(ROOT, "src", "silo_manager")):
    if p not in sys.path:
        sys.path.append(p)

import markets  # noqa: E402
import pipeline  # noqa: E402


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Markets(unittest.TestCase):
    def test_implied_probabilities_remove_the_margin(self):
        p, over = markets.implied_probabilities([1.9, 1.9])
        self.assertAlmostEqual(float(p.sum()), 1.0)
        self.assertAlmostEqual(float(p[0]), 0.5)
        self.assertGreater(over, 0.05)

    def test_bad_odds_are_refused(self):
        for bad in ([1.0, 2.0], [2.0], [0.5, 3.0]):
            with self.assertRaises(ValueError):
                markets.implied_probabilities(bad)

    def test_kelly_is_never_negative_and_is_capped(self):
        self.assertEqual(markets.kelly_fraction(0.4, 2.0), 0.0)            # no edge, no stake
        self.assertEqual(markets.kelly_fraction(0.99, 10.0), 0.25)          # capped
        self.assertGreater(markets.kelly_fraction(0.6, 2.0), 0.0)

    def test_elo_conserves_points_and_rewards_an_upset(self):
        a, b, exp = markets.elo_update(1400, 1600, 1)                       # the weaker side wins
        self.assertAlmostEqual((a + b), 3000.0)
        self.assertGreater(a - 1400, 10)

    def test_return_stats_and_drawdown(self):
        s = markets.return_stats([0.01, -0.005, 0.004, 0.006, 0.002] * 20)
        self.assertEqual(s["n"], 100)
        self.assertAlmostEqual(s["p_up"], 0.8)
        self.assertLess(s["p_up_low"], 0.8)
        self.assertAlmostEqual(markets.max_drawdown([100, 120, 90, 110]), 0.25)
        with self.assertRaises(ValueError):
            markets.return_stats([0.01])

    def test_ab_test_needs_traffic(self):
        small = markets.ab_test(2, 40, 4, 40)
        big = markets.ab_test(30, 1000, 55, 1000)
        self.assertFalse(small["significant"])
        self.assertTrue(big["significant"])
        self.assertLess(big["p_value"], 0.01)


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.p = pipeline.SiloPipeline("t", {"entropy": {"drift_tolerance": 0.1}, "signal": {"min_volatility": 0.4}, "risk": {"exposure_limit": 0.5},
                                              "thershold": {"threshold_value": 0.6}, "stratagy": {"threshold": 0.7, "action_high": "GO", "action_low": "WAIT"},
                                              "feedback": {"learning_rate": 0.25}})

    def test_a_small_sample_cannot_pass_with_a_perfect_record(self):
        r = self.p.run({"successes": 5, "trials": 5})
        self.assertEqual(r["action"], "WAIT")
        self.assertLess(r["probability"]["low"], 0.7)

    def test_a_large_consistent_sample_passes(self):
        r = self.p.run({"successes": 900, "trials": 1000})
        self.assertEqual(r["action"], "GO")
        self.assertEqual(r["reasons"], [])

    def test_drift_vetoes_even_a_strong_record(self):
        r = self.p.run({"successes": 900, "trials": 1000, "drift": 0.5})
        self.assertEqual(r["action"], "WAIT")
        self.assertTrue(r["vetoed"])
        self.assertIn("drifting", r["reasons"][0])

    def test_a_stagnant_signal_vetoes(self):
        r = self.p.run({"successes": 900, "trials": 1000, "volatility": 0.1, "direction": "up"})
        self.assertEqual(r["action"], "WAIT")

    def test_risk_above_the_limit_vetoes(self):
        r = self.p.run({"samples": [1] * 50 + [20] * 50, "limit": 10})          # half the samples exceed the limit
        self.assertEqual(r["action"], "WAIT")
        self.assertEqual(r["gates"]["risk"]["verdict"], "RISK_HIGH")

    def test_every_decision_carries_its_reasons_and_a_disclaimer(self):
        r = self.p.run({"successes": 3, "trials": 10})
        self.assertIn("not advice", r["disclaimer"])
        self.assertTrue(r["reasons"])

    def test_missing_evidence_is_refused(self):
        with self.assertRaises(ValueError):
            self.p.run({"drift": 0.0})

    def test_calibration_report_needs_outcomes_then_measures(self):
        self.assertIn("not enough", self.p.calibration_report()["note"])
        rng = np.random.default_rng(3)
        for _ in range(200):
            prob = float(rng.uniform(0.2, 0.8))
            self.p.record_outcome(prob, int(rng.uniform() < prob))
        rep = self.p.calibration_report()
        self.assertEqual(rep["n"], 200)
        self.assertLess(rep["brier"], 0.30)

    def test_silo_parameter_files_are_read_and_do_not_shadow_stdlib_signal(self):
        params = pipeline.load_silo_params(os.path.join(ROOT, "sports"))
        self.assertEqual(params["stratagy"]["action_high"], "BET")
        import signal as stdlib_signal
        self.assertTrue(hasattr(stdlib_signal, "SIGINT"))


class Silos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sports = load("sports/sports.py", "t_sports").SportsEngine()
        cls.stocks = load("stocks/stocks.py", "t_stocks").StocksEngine()
        cls.ecom = load("ecom/ecom.py", "t_ecom").EcomEngine()

    def test_sports_needs_an_edge_not_just_a_good_record(self):
        r = self.sports.calculate({"wins": 70, "games": 100, "decimal_odds": [1.6, 5.0]})        # a strong team, but the odds already say so
        self.assertEqual(r["action"], "PASS")
        self.assertLessEqual(r["market"]["edge_using_lower_bound"], 0)
        self.assertEqual(r["suggested_stake_fraction"], 0.0)

    def test_sports_can_recommend_when_every_gate_and_the_edge_agree(self):
        r = self.sports.calculate({"wins": 800, "games": 1000, "decimal_odds": [1.6, 5.0]})
        self.assertEqual(r["action"], "BET")
        self.assertGreater(r["suggested_stake_fraction"], 0)
        self.assertLessEqual(r["suggested_stake_fraction"], 0.25)

    def test_stocks_do_not_buy_on_a_short_history(self):
        r = self.stocks.calculate({"returns": [0.01, 0.02, 0.01, 0.03, 0.02]})
        self.assertEqual(r["action"], "WAIT")
        self.assertEqual(r["stats"]["n"], 5)

    def test_stocks_report_drawdown_when_given_prices(self):
        r = self.stocks.calculate({"returns": [0.01, -0.01] * 10, "prices": [100, 120, 90, 110]})
        self.assertAlmostEqual(r["max_drawdown"], 0.25)

    def test_ecom_holds_without_significance_and_adjusts_with_it(self):
        small = self.ecom.calculate({"control": {"visitors": 40, "orders": 2}, "variant": {"visitors": 40, "orders": 4}})
        big = self.ecom.calculate({"control": {"visitors": 1000, "orders": 30}, "variant": {"visitors": 1000, "orders": 55}})
        self.assertEqual(small["action"], "HOLD")
        self.assertEqual(big["action"], "ADJUST")


class Logistics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logs = load("logs/logs.py", "t_logs").LogsEngine()

    def test_queue_metrics_match_known_values(self):
        m = markets.queue_metrics(8, 10)                       # M/M/1 at 80 % load: P(wait) = 0.8, Wq = 0.4
        self.assertAlmostEqual(m["utilization"], 0.8)
        self.assertAlmostEqual(m["p_wait"], 0.8)
        self.assertAlmostEqual(m["avg_wait"], 0.4)
        self.assertFalse(markets.queue_metrics(10, 10)["stable"])
        self.assertGreater(markets.queue_metrics(8, 10, servers=1)["avg_wait"], markets.queue_metrics(8, 10, servers=2)["avg_wait"])

    def test_restock_needs_enough_evidence(self):
        few = self.logs.calculate({"lead_time_demand": [50, 60, 70], "on_hand": 10})            # always short, but only 3 observations
        many = self.logs.calculate({"lead_time_demand": list(range(40, 140)), "on_hand": 20})   # short in every one of 100 lead times
        self.assertEqual(few["action"], "MONITOR")
        self.assertEqual(many["action"], "RESTOCK")
        self.assertGreater(many["stock"]["reorder_level_95"], 120)

    def test_the_bottleneck_is_the_busiest_stage(self):
        r = self.logs.calculate({"lead_time_demand": [10, 20, 30, 40], "on_hand": 100,
                                 "stages": [{"name": "pick", "arrival_rate": 5, "service_rate": 10}, {"name": "pack", "arrival_rate": 5, "service_rate": 6}]})
        self.assertEqual(r["bottleneck"], "pack")


class Manager(unittest.TestCase):
    def test_the_silo_manager_runs_every_silo(self):
        pkg = load("src/silo_manager/__init__.py", "t_manager")
        m = pkg.SiloManager()
        self.assertEqual(m.available(), ["ecom", "logs", "sports", "stocks"])
        self.assertEqual(set(m.health().values()), {"OK"})
        self.assertEqual(m.run_silo("stocks", {"returns": [0.01, -0.01] * 5})["engine"], "Stocks Engine")
        with self.assertRaises(KeyError):
            m.engine("nope")

    def test_lib_can_be_imported_as_a_package(self):
        # a regression guard: an eager import in lib/__init__.py once made every `import lib.x` fail, and the risk engine silently stopped measuring
        import importlib
        sys.modules.pop("lib", None)
        for k in [k for k in sys.modules if k.startswith("lib.")]:
            sys.modules.pop(k)
        sys.path.insert(0, ROOT)
        try:
            importlib.import_module("lib.probability")
        finally:
            sys.path.remove(ROOT)

    def test_risk_refuses_to_guess_when_it_cannot_measure(self):
        risk = load("src/silo_manager/risk.py", "t_risk")
        eng = risk.RiskEngine("t", 0.5)
        saved = risk.failure_probability
        risk.failure_probability = None
        try:
            with self.assertRaises(RuntimeError):
                eng.calculate({"samples": [1, 2, 3], "limit": 2})
        finally:
            risk.failure_probability = saved


class Gatekeeper(unittest.TestCase):
    def test_the_gatekeeper_reads_real_files_and_refuses_the_rest(self):
        import manager
        ds = manager.load("data_source").DataSource("TEST")
        self.assertEqual(ds.fetch()["status"], "ERROR")                       # not connected
        self.assertFalse(ds.connect(os.path.join(tempfile.gettempdir(), "does_not_exist.json")))
        d = tempfile.mkdtemp(prefix="gate_")
        jp, cp = os.path.join(d, "a.json"), os.path.join(d, "a.csv")
        json.dump({"games": 3}, open(jp, "w"))
        open(cp, "w").write("team,wins\nA,3\nB,5\n")
        self.assertTrue(ds.connect(jp))
        self.assertEqual(ds.fetch()["data"], {"games": 3})
        self.assertTrue(ds.connect(cp))
        self.assertEqual(ds.fetch()["data"][1]["wins"], "5")
        txt = os.path.join(d, "a.txt")
        open(txt, "w").write("x")
        ds.connect(txt)
        self.assertEqual(ds.fetch()["status"], "ERROR")


if __name__ == "__main__":
    unittest.main(verbosity=1)
