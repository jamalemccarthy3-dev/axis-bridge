"""test_portals.py - the four command-deck portals (Sports, Markets, Logistics, Economics): the axis-logic worker's maths, the field catalog and its search (axis-core), Add to Hub
mounting, the bridge routes, and the page's strict dock order. Nothing here touches the network. Run: python test_portals.py"""
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="portals_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(TMP, "data"))
sys.path.insert(0, ROOT)
import portal_fixtures  # noqa: E402
portal_fixtures.write(os.path.join(TMP, "data"), ROOT)                       # test fixtures + the real field catalog; the shipped portal_data/ holds no data
os.environ.update(NEXXUS_PORTAL_DATA=os.path.join(TMP, "data"), NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "cr"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"),
                  NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"), NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1")
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import portals as P  # noqa: E402
import python_server as srv  # noqa: E402

PAGE = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "render", "babylon_preview.html")
with open(PAGE, encoding="utf-8") as _f:
    HTML = _f.read()
SILO = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault")


def run(op, **args):
    return P.run(op, args)["result"]


class Worker(unittest.TestCase):
    def test_sports_edge_is_a_decision_record_that_stakes_nothing(self):
        r = run("sports.evaluate", wins=30, games=50, decimal_odds=[1.8, 2.1], outcome_index=0)
        self.assertLess(r["probability"]["low"], r["probability"]["point"])
        self.assertLess(r["probability"]["point"], r["probability"]["high"])
        self.assertIn("implied_probability", r["market"])
        self.assertEqual(r["engine"], "Sports Engine")

    def test_a_tiny_record_cannot_recommend(self):
        r = run("sports.evaluate", wins=3, games=3, decimal_odds=[1.3, 3.5], outcome_index=0)
        self.assertNotIn(r["action"], ("BET", "BUY"))

    def test_parlay_filter_and_price(self):
        legs = [{"label": "a", "odds": 1.9, "p": 0.6, "platform": "book"}, {"label": "b", "odds": 2.0, "p": 0.55, "platform": "book"}, {"label": "c", "odds": 1.95, "p": 0.5, "platform": "casino"}]
        r = run("sports.parlay", legs=legs, platforms=["book"])
        self.assertEqual([g["label"] for g in r["kept"]], ["a", "b"])
        self.assertEqual(r["dropped"][0]["label"], "c")
        self.assertAlmostEqual(r["combined_odds"], 3.8)
        self.assertAlmostEqual(r["model_probability"], 0.33)
        self.assertAlmostEqual(r["edge"], 0.33 - 1 / 3.8)
        self.assertLessEqual(r["kelly_fraction"], 0.25)
        everything_out = run("sports.parlay", legs=legs, platforms=["nowhere"])
        self.assertEqual(everything_out["legs"], 0)
        with self.assertRaises(P.PortalError):
            run("sports.parlay", legs=[{"label": "x", "odds": 1.0}])

    def test_team_matrix_leaders_respect_lower_is_better(self):
        r = run("sports.compare", teams=[{"name": "A", "wins": 30, "games": 40, "stats": {"pts": 110, "tov": 12}}, {"name": "B", "wins": 10, "games": 40, "stats": {"pts": 100, "tov": 15}}], lower_is_better=["tov"])
        self.assertEqual(r["leaders"], {"pts": "A", "tov": "A"})
        self.assertTrue(r["records_clearly_different"])
        close = run("sports.compare", teams=[{"name": "A", "wins": 6, "games": 10}, {"name": "B", "wins": 5, "games": 10}])
        self.assertFalse(close["records_clearly_different"])

    def test_player_queries(self):
        players = [{"name": "X", "seasons": [{"season": 2020, "pts": 20}, {"season": 2021, "pts": 25}, {"season": 2022, "pts": 22}, {"season": 2023, "pts": 18}]}]
        c = run("sports.player", players=players, player="x", stat="pts", mode="career")
        self.assertEqual((c["career_total"], c["per_season"], c["best_season"]["season"]), (85.0, 21.25, 2021))
        s = run("sports.player", players=players, player="X", stat="pts", mode="season", season=2022)
        self.assertEqual((s["value"], s["rank_among_own_seasons"]), (22, 2))
        with self.assertRaises(P.PortalError):
            run("sports.player", players=players, player="nobody", stat="pts")

    def test_markets_analysis_and_cone(self):
        rets = [0.01, -0.005, 0.012, 0.003, -0.02, 0.015, 0.004, -0.001, 0.008, 0.006, -0.012, 0.009]
        a = run("markets.analyze", returns=rets, prices=[100, 101, 99, 103, 104])
        self.assertLess(a["stats"]["p_up_low"], a["stats"]["p_up"])
        self.assertNotEqual(a["action"], "BUY")                     # twelve days cannot buy
        f = run("markets.forecast", returns=rets, start_price=100, days=30, seed=1)
        self.assertEqual(len(f["bands"]["50"]), 30)
        for i in range(30):
            self.assertLessEqual(f["bands"]["5"][i], f["bands"]["50"][i])
            self.assertLessEqual(f["bands"]["50"][i], f["bands"]["95"][i])
        self.assertEqual(f, run("markets.forecast", returns=rets, start_price=100, days=30, seed=1))        # seeded: the same question gets the same cone
        with self.assertRaises(P.PortalError):
            run("markets.forecast", returns=[0.1, 0.2])

    def test_logistics_maths(self):
        q = run("logistics.queue", arrival_rate=3, service_rate=4, servers=1)
        self.assertTrue(q["stable"])
        self.assertAlmostEqual(q["utilization"], 0.75)
        self.assertAlmostEqual(q["avg_wait"], 0.75, places=6)                      # M/M/1: rho / (mu - lambda)
        u = run("logistics.queue", arrival_rate=5, service_rate=4, servers=1)
        self.assertFalse(u["stable"])
        self.assertIsNone(u["avg_wait"])                                           # infinity is never sent as a number (browsers reject it)
        e = run("logistics.eoq", annual_demand=12000, order_cost=50, holding_cost=2.5)
        self.assertAlmostEqual(e["order_quantity"], (2 * 12000 * 50 / 2.5) ** 0.5)
        s = run("logistics.stockout", lead_time_demands=[40, 55, 60, 48, 70, 52], on_hand=58)
        self.assertAlmostEqual(s["stockout_rate"], 2 / 6)
        o = run("logistics.ontime", delivered=200, on_time=181)
        self.assertLess(o["low"], o["rate"])
        with self.assertRaises(P.PortalError):
            run("logistics.ontime", delivered=10, on_time=11)
        t = run("logistics.fulfillment_test", control={"delivered": 20, "on_time": 10}, variant={"delivered": 20, "on_time": 12})
        self.assertFalse(t["significant"])                                         # a small sample is never a win

    def test_economics_known_answers(self):
        self.assertAlmostEqual(run("economics.model", kind="loan", principal=250000, rate=0.06, years=30)["payment"], 1498.88, places=2)
        n = run("economics.model", kind="npv", rate=0.08, cash_flows=[-1000, 300, 400, 500, 200])
        self.assertAlmostEqual(n["npv"], 164.635, places=2)
        self.assertAlmostEqual(n["irr"], 0.15322, places=4)
        self.assertIsNone(run("economics.model", kind="npv", rate=0.05, cash_flows=[100, 100, 100])["irr"])      # no sign change: no rate exists
        self.assertAlmostEqual(run("economics.model", kind="real_rate", nominal=0.05, inflation=0.03)["real_rate"], 1.05 / 1.03 - 1)
        self.assertAlmostEqual(run("economics.model", kind="cagr", start=100, end=200, years=10)["cagr"], 2 ** 0.1 - 1)
        t = run("economics.model", kind="trend", values=[100, 102, 101, 105, 107, 110, 109, 113], horizon=3)
        self.assertEqual(len(t["projection"]), 3)
        self.assertTrue(t["slope_is_distinguishable_from_zero"])
        flat = run("economics.model", kind="trend", values=[5, 6, 5, 6, 5, 6, 5, 6])
        self.assertFalse(flat["slope_is_distinguishable_from_zero"])
        for bad in (dict(kind="cagr", start=-1, end=2, years=3), dict(kind="loan", principal=0, rate=0.05, years=5), dict(kind="trend", values=[1, 2, 3]), dict(kind="bogus")):
            with self.assertRaises(P.PortalError):
                run("economics.model", **bad)

    def test_unknown_and_malformed_requests_are_clean_errors(self):
        with self.assertRaises(P.PortalError):
            P.run("os.system", {})
        with self.assertRaises(P.PortalError):
            run("sports.evaluate", wins=3)                                         # missing field
        with self.assertRaises(P.PortalError):
            P.run("economics.model", {"kind": "loan", "principal": "x"})

    def test_the_compute_side_makes_no_outside_calls(self):
        for rel in (("axis-logic", "portal_worker.py"), ("axis-logic", "lib", "economics.py"), ("axis-logic", "lib", "logistics.py"), ("axis-core", "hub_search.py")):
            src = open(os.path.join(SILO, *rel), encoding="utf-8").read()
            self.assertIsNone(re.search(r"^\s*(import|from)\s+(requests|urllib|http|socket|ftplib|smtplib|subprocess|webbrowser)\b", src, re.M), rel)


class RealDataOnly(unittest.TestCase):
    """The portals run on the owner's real data or on nothing: a schema, mandatory provenance, and no sample, placeholder, demo or mock data."""

    def setUp(self):
        import portal_schemas
        self.S = portal_schemas
        self.docs = portal_fixtures.fixtures()
        self.dir = P.DATA_DIR
        self._backup = {n: (self.dir / (n + ".json")).read_bytes() for n in self.docs if (self.dir / (n + ".json")).exists()}

    def tearDown(self):
        for n in self.docs:
            p = self.dir / (n + ".json")
            p.write_bytes(self._backup[n]) if n in self._backup else (p.unlink() if p.exists() else None)

    def test_every_fixture_passes_its_own_schema(self):
        for n, doc in self.docs.items():
            self.assertEqual(self.S.validate(n, doc), [], n)

    def test_provenance_is_mandatory(self):
        for n, doc in self.docs.items():
            bad = dict(doc)
            bad.pop("source")
            self.assertTrue(any("source is required" in e for e in self.S.validate(n, bad)), n)
            self.assertTrue(any("source is required" in e for e in self.S.validate(n, dict(doc, source="   "))), n)

    def test_sample_placeholder_demo_and_mock_data_is_rejected(self):
        t = self.docs["teams"]
        self.assertTrue(any("marked sample" in e for e in self.S.validate("teams", dict(t, sample=True))))
        for word in ("sample", "placeholder", "demo", "mock", "fake", "dummy", "lorem", "example"):
            self.assertTrue(any("placeholder" in e for e in self.S.validate("teams", dict(t, source="my %s data" % word))), word)
            bad = dict(t, teams=[dict(t["teams"][0], name="%s Team" % word.title())] + t["teams"][1:])
            self.assertTrue(any("placeholder" in e for e in self.S.validate("teams", bad)), word)
        self.assertEqual(self.S.validate("teams", dict(t, source="NBA.com stats export, 2026-10-11")), [])               # real provenance passes

    def test_rows_must_follow_the_schema(self):
        cases = {
            "teams": [{"name": "A", "wins": 50, "games": 40}, {"name": "A", "wins": -1, "games": 40}, {"name": "A", "wins": 1.5, "games": 40}, {"name": "A", "games": 40}, {"name": "", "wins": 1, "games": 2}],
            "legs": [{"label": "x", "odds": 1.0, "platform": "p"}, {"label": "x", "odds": 2.0, "platform": "p", "p": 1.2}, {"label": "x", "odds": "2", "platform": "p"}],
            "series": [{"symbol": "A", "start_price": 0, "returns": [0.01] * 20}, {"symbol": "A", "start_price": 5, "returns": [0.01] * 3}, {"symbol": "A", "start_price": 5, "returns": [-1.5] + [0.01] * 12}],
            "macro": [{"name": "A", "unit": "x", "values": [1, 2, 3]}, {"name": "A", "unit": "x", "values": [1, 2, 3, 4, "5"]}],
            "assets": [{"id": "1", "name": "n", "kind": "k", "status": "s"}, {"id": "1", "name": "n", "kind": "k", "status": "s", "location": 5}],
            "players": [{"name": "A", "seasons": []}, {"name": "A", "seasons": [{"season": 1500, "pts": 1}]}, {"name": "A", "seasons": [{"season": 2020}]}, {"name": "A", "seasons": [{"season": 2020, "pts": "9"}]}],
            "ticker": [{"kind": "rumour", "text": "x"}, {"kind": "live", "text": ""}],
        }
        for name, rows in cases.items():
            key = self.S.SCHEMAS[name]["list"]
            for row in rows:
                self.assertTrue(self.S.validate(name, {"source": "a real source", key: [row]}), (name, row))
            self.assertTrue(self.S.validate(name, {"source": "a real source", key: []}), name)                         # an empty file is not a data set
        two = {"source": "a real source", "teams": [{"name": "A", "wins": 1, "games": 2}, {"name": "a", "wins": 1, "games": 2}]}
        self.assertTrue(any("appears twice" in e for e in self.S.validate("teams", two)))
        self.assertTrue(self.S.validate("teams", "text") and self.S.validate("teams", []) and self.S.validate("nope", {}))

    def test_a_missing_data_set_is_reported_as_not_loaded_with_its_schema(self):
        (self.dir / "series.json").unlink()
        d = P.data("series")
        self.assertTrue(d["missing"])
        self.assertIn("series", d["schema"])
        self.assertIn("source: text (where this data came from, required)", d["schema"])
        self.assertNotIn("rows", d)

    def test_a_rejected_file_is_unused_and_says_why(self):
        (self.dir / "teams.json").write_text(json.dumps(dict(self.docs["teams"], sample=True)), encoding="utf-8")
        d = P.data("teams")
        self.assertTrue(d["invalid"])
        self.assertTrue(any("marked sample" in e for e in d["errors"]))
        self.assertNotIn("teams", d)                                                         # none of its content leaks through
        (self.dir / "teams.json").write_text("{broken", encoding="utf-8")
        self.assertTrue(P.data("teams")["invalid"])

    def test_save_writes_only_a_valid_whole_file(self):
        (self.dir / "legs.json").unlink()
        with self.assertRaises(P.PortalError):
            P.save_data("legs", {"source": "my sample sheet", "legs": self.docs["legs"]["legs"]})
        self.assertFalse((self.dir / "legs.json").exists())                                   # nothing half-written
        res = P.save_data("legs", dict(self.docs["legs"], source="bookmaker export 2026-10-11"))
        self.assertEqual((res["row_count"], res["source"]), (5, "bookmaker export 2026-10-11"))
        self.assertEqual(P.data("legs")["source"], "bookmaker export 2026-10-11")
        self.assertFalse([f for f in os.listdir(self.dir) if f.endswith(".tmp")])
        with self.assertRaises(P.PortalError):
            P.save_data("../../etc", {})

    def test_every_calculator_has_a_documented_argument_schema(self):
        for op in P.ALL_OPS:
            self.assertIn(op, self.S.OP_ARGS, op)
            self.assertTrue(self.S.OP_ARGS[op].strip())
        self.assertEqual(set(self.S.OP_ARGS), set(P.ALL_OPS))

    def test_state_and_the_prompt_block_are_the_real_picture(self):
        st = P.state("logistics")
        self.assertEqual([d["status"] for d in st["data"]], ["loaded"])
        self.assertEqual(st["data"][0]["row_count"], 14)
        txt = self.S.prompt_block(st)
        self.assertIn("data set assets: LOADED, 14 rows, source: unit-test fixture", txt)
        self.assertIn("logistics.eoq(annual_demand:number>0, order_cost:number>0, holding_cost:number>0)", txt)
        self.assertIn("never invent a score, price, rate, row, name or statistic", txt)
        (self.dir / "assets.json").unlink()
        gone = self.S.prompt_block(P.state("logistics"))
        self.assertIn("data set assets: NOT LOADED", gone)
        self.assertNotIn("14 rows", gone)
        (self.dir / "assets.json").write_text(json.dumps({"source": "x", "assets": [{"id": "1"}]}), encoding="utf-8")
        self.assertIn("REJECTED", self.S.prompt_block(P.state("logistics")))

    def test_the_shipped_portal_data_folder_holds_no_data(self):
        shipped = set(os.listdir(os.path.join(ROOT, "portal_data")))
        self.assertEqual(shipped - {"hub_catalog.json"} - {n + ".json" for n in self.docs} - {"hub_%s.json" % k for k in P.ORDER}, set())
        try:
            tracked = subprocess.run(["git", "-C", ROOT, "ls-files", "portal_data"], capture_output=True, text=True, timeout=30).stdout.split()
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git is not available")
        self.assertEqual(tracked, ["portal_data/hub_catalog.json"])                           # the only tracked file is the real tool catalog


class Catalog(unittest.TestCase):
    def entries(self):
        return json.load(open(os.path.join(ROOT, "portal_data", "hub_catalog.json"), encoding="utf-8"))["entries"]

    def test_every_entry_is_well_formed(self):
        seen = set()
        for e in self.entries():
            for k in ("id", "portal", "name", "kind", "category", "access", "rating", "summary", "tags"):
                self.assertIn(k, e, e.get("id"))
            self.assertNotIn(e["id"], seen)
            seen.add(e["id"])
            self.assertIn(e["portal"], P.ORDER)
            self.assertIn(e["kind"], ("api", "database", "calculator", "feed", "platform", "library"))
            self.assertIn(e["rating"], (1, 2, 3, 4, 5))
            self.assertIsInstance(e["key_required"], bool)
            self.assertTrue(e["url"] == "" or re.match(r"^https?://\S+$", e["url"]), e["id"])
            if e["access"] == "built-in":
                self.assertEqual(e["url"], "")
                tab = e["builtin"]["tab"]
                self.assertRegex(HTML, r"\['%s', '[A-Za-z ]+'\]" % tab, "%s: the page has no %r tab" % (e["id"], tab))
            else:
                self.assertNotIn("builtin", e)
                self.assertNotEqual(e["url"], "", e["id"])

    def test_every_field_is_broad_and_says_it_is_editorial(self):
        doc = json.load(open(os.path.join(ROOT, "portal_data", "hub_catalog.json"), encoding="utf-8"))
        self.assertTrue(doc["editorial"])
        self.assertIn("NOT fetched live", doc["source"])
        for k in P.ORDER:
            rows = [e for e in doc["entries"] if e["portal"] == k]
            self.assertGreaterEqual(len(rows), 15, k)
            self.assertGreaterEqual(len({e["category"] for e in rows}), 4, k)
            self.assertGreaterEqual(len({e["kind"] for e in rows}), 4, k)


class Search(unittest.TestCase):
    def search(self, portal, query="", kind=None):
        return P.run("hub.search", {"portal": portal, "query": query, "kind": kind, "limit": 60})["result"]

    def test_the_whole_field_is_searched_and_only_that_field(self):
        for k in P.ORDER:
            r = self.search(k)
            self.assertEqual(r["matched"], r["total_in_field"])
            self.assertTrue(all(e["portal"] == k for e in r["results"]))
            self.assertEqual(sum(r["breakdown"].values()), r["matched"])

    def test_field_wide_queries_find_what_the_brief_lists(self):
        names = lambda p, q: [e["name"] for e in self.search(p, q)["results"]]  # noqa: E731
        self.assertIn("The Odds API", names("sports", "odds"))
        self.assertIn("Retrosheet", names("sports", "historical"))
        self.assertIn("Betfair Exchange API", names("sports", "betting platform"))
        self.assertIn("CoinGecko API", names("markets", "crypto"))
        self.assertIn("QuantLib", names("markets", "options"))
        self.assertIn("Probability workspace", names("markets", "probability"))
        self.assertIn("AfterShip", names("logistics", "tracking"))
        self.assertIn("ERPNext", names("logistics", "warehouse"))
        self.assertIn("Google OR-Tools", names("logistics", "route"))
        self.assertIn("Zillow Research Data", names("economics", "housing"))
        self.assertIn("US Census Bureau API", names("economics", "demographics"))
        self.assertIn("FRED API", names("economics", "inflation"))

    def test_ranking_breakdown_and_best_in_class(self):
        r = self.search("economics", "housing")
        self.assertEqual(r["results"][0]["name"], "S&P CoreLogic Case-Shiller indices")           # rating 5, best match
        scores = [e["score"] for e in r["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for cat, eid in r["best_in_class"].items():
            top = max(e["rating"] for e in r["results"] if e["category"] == cat)
            self.assertEqual(next(e for e in r["results"] if e["id"] == eid)["rating"], top)

    def test_kind_filter_nonsense_and_inputs(self):
        self.assertTrue(all(e["kind"] == "api" for e in self.search("economics", "gdp", "api")["results"]))
        self.assertEqual(self.search("economics", "zzzqqq")["matched"], 0)
        self.assertEqual(self.search("sports", "<script>alert(1)</script>")["matched"], 0)
        self.assertEqual(self.search("sports", "x" * 5000)["query"], "x" * 120)
        with self.assertRaises(P.PortalError):
            self.search("bogus", "odds")


class Mounts(unittest.TestCase):
    def setUp(self):
        for k in P.ORDER:
            p = P._mount_path(k)
            if p.exists():
                p.unlink()

    def test_add_remove_and_order(self):
        self.assertEqual(P.hub_mounted("sports"), [])
        P.hub_set("sports", "sp-parlay", True)
        P.hub_set("sports", "sp-oddsapi", True)
        P.hub_set("sports", "sp-parlay", True)                                      # adding twice changes nothing
        self.assertEqual([e["id"] for e in P.hub_mounted("sports")], ["sp-parlay", "sp-oddsapi"])
        P.hub_set("sports", "sp-parlay", False)
        self.assertEqual([e["id"] for e in P.hub_mounted("sports")], ["sp-oddsapi"])
        self.assertEqual(P.hub_mounted("markets"), [])                              # each portal keeps its own hub

    def test_only_catalog_entries_of_that_portal_can_be_mounted(self):
        for portal, eid in (("sports", "ec-fred"), ("sports", "../../etc/passwd"), ("sports", ""), ("bogus", "sp-edge")):
            with self.assertRaises(P.PortalError):
                P.hub_set(portal, eid, True)
        self.assertFalse(P._mount_path("sports").exists())

    def test_cap_and_survival_of_a_removed_catalog_entry(self):
        ids = [e["id"] for e in P.hub_entries("economics")]
        P.MAX_MOUNTED, cap = 2, P.MAX_MOUNTED
        try:
            P.hub_set("economics", ids[0], True)
            P.hub_set("economics", ids[1], True)
            with self.assertRaises(P.PortalError):
                P.hub_set("economics", ids[2], True)
            P.hub_set("economics", ids[0], False)                                       # removing one makes room again
            P.hub_set("economics", ids[2], True)
            self.assertEqual([e["id"] for e in P.hub_mounted("economics")], [ids[1], ids[2]])
        finally:
            P.MAX_MOUNTED = cap
        with open(P._mount_path("sports"), "w", encoding="utf-8") as f:
            json.dump({"mounted": ["sp-edge", "gone-from-catalog"]}, f)
        self.assertEqual([e["id"] for e in P.hub_mounted("sports")], ["sp-edge"])       # an id that left the catalog just drops out

    def test_a_corrupt_mount_file_reads_as_empty(self):
        P._mount_path("markets").write_text("{not json", encoding="utf-8")
        self.assertEqual(P.hub_mounted("markets"), [])


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()

    def setUp(self):
        Mounts.setUp(self)

    def test_catalog_lists_the_four_portals_in_dock_order(self):
        c = self.http.get("/api/portals").get_json()
        self.assertEqual(c["order"], ["sports", "markets", "logistics", "economics"])
        self.assertTrue(c["available"] and c["hub"]["editorial"])
        self.assertIn("No bet, trade, order or shipment", c["no_execution"])

    def test_data_reports_what_it_really_is_and_unknown_names_are_refused(self):
        d = self.http.get("/api/portals/data/ticker").get_json()["data"]
        self.assertEqual((d["row_count"], d["name"]), (3, "ticker"))
        self.assertEqual(len(d["rows"]), 3)                                                    # the file's own rows, not the count
        self.assertNotIn("sample", d)
        self.assertEqual(self.http.get("/api/portals/data/passwd").status_code, 404)
        self.assertEqual(self.http.get("/api/portals/data/..%2F..%2Fpython_server").status_code, 404)

    def test_saving_a_data_set_needs_the_admin_token_and_a_valid_file(self):
        doc = dict(portal_fixtures.fixtures()["teams"], source="league export 2026-10-11")
        self.assertEqual(self.http.post("/api/portals/data/teams", json={"doc": doc}).status_code, 401)
        head = {"X-Nexxus-Admin-Token": "throwaway-admin"}
        bad = self.http.post("/api/portals/data/teams", json={"doc": dict(doc, sample=True)}, headers=head)
        self.assertEqual(bad.status_code, 400)
        self.assertIn("marked sample", bad.get_json()["message"])
        self.assertEqual(self.http.post("/api/portals/data/teams", json={}, headers=head).status_code, 400)
        self.assertEqual(self.http.post("/api/portals/data/passwd", json={"doc": doc}, headers=head).status_code, 400)
        ok = self.http.post("/api/portals/data/teams", json={"doc": doc}, headers=head)
        self.assertEqual((ok.status_code, ok.get_json()["saved"]["row_count"]), (200, 3))
        self.assertEqual(self.http.get("/api/portals/data/teams").get_json()["data"]["source"], "league export 2026-10-11")

    def test_run_and_its_refusals(self):
        r = self.http.post("/api/portals/run", json={"op": "economics.model", "args": {"kind": "cagr", "start": 100, "end": 180, "years": 8}})
        self.assertEqual(r.status_code, 200)
        self.assertAlmostEqual(r.get_json()["result"]["cagr"], 0.07624, places=4)
        self.assertGreaterEqual(r.get_json()["ms"], 0)
        for body in ({"op": "nope"}, {"args": {}}, "text", {"op": "economics.model", "args": {"kind": "cagr", "start": -1, "end": 2, "years": 3}}):
            self.assertEqual(self.http.post("/api/portals/run", json=body).status_code, 400, body)

    def test_a_fourth_simultaneous_calculation_is_turned_away_politely(self):
        held = [P._SLOTS.acquire(blocking=False) for _ in range(3)]
        try:
            r = self.http.post("/api/portals/run", json={"op": "economics.model", "args": {"kind": "cagr", "start": 1, "end": 2, "years": 1}})
            self.assertEqual(r.status_code, 429)
            self.assertEqual(r.get_json()["status"], "busy")
        finally:
            for ok in held:
                if ok:
                    P._SLOTS.release()

    def test_search_and_add_to_hub_through_the_routes(self):
        s = self.http.post("/api/portals/run", json={"op": "hub.search", "args": {"portal": "logistics", "query": "freight"}}).get_json()["result"]
        self.assertGreater(s["matched"], 0)
        first = s["results"][0]["id"]
        self.assertEqual(self.http.get("/api/portals/hub/logistics").get_json()["mounted"], [])
        m = self.http.post("/api/portals/hub/mount", json={"portal": "logistics", "id": first, "action": "add"}).get_json()
        self.assertEqual([e["id"] for e in m["mounted"]], [first])
        self.assertEqual([e["id"] for e in self.http.get("/api/portals/hub/logistics").get_json()["mounted"]], [first])
        self.assertEqual(self.http.post("/api/portals/hub/mount", json={"portal": "sports", "id": first, "action": "add"}).status_code, 400)
        self.assertEqual(self.http.post("/api/portals/hub/mount", json={"portal": "logistics", "id": first, "action": "burn"}).status_code, 400)
        self.assertEqual(self.http.get("/api/portals/hub/bogus").status_code, 404)
        self.http.post("/api/portals/hub/mount", json={"portal": "logistics", "id": first, "action": "remove"})
        self.assertEqual(self.http.get("/api/portals/hub/logistics").get_json()["mounted"], [])


class PageSource(unittest.TestCase):
    def test_the_strict_ribbon_order(self):
        ids = ("dockPt_sports", "dockPt_markets", "dockPt_logistics", "dockPt_economics", "dockHomeBtn", "dockLinkBtn", "dockBuildBtn")
        order = [HTML.index('id="%s"' % i) for i in ids]
        self.assertEqual(order, sorted(order))
        self.assertLess(order[-1], HTML.index('id="dockPerimBtn"'))
        self.assertLess(HTML.index('id="axisDock"'), order[0])

    def test_the_panel_and_its_pieces(self):
        for needle in ('id="dockPortal"', 'id="ptQ"', 'id="ptKind"', 'id="ptTabs"', 'id="dockPortalBody"', "'+ ADD TO HUB'", "function ptSearchView", "function ptHub", "function ptMount",
                       "backdrop-filter:blur(18px)", "body.perim-open #dockPortal", "'api/portals/run'", "'api/portals/hub/mount'"):
            self.assertIn(needle, HTML, needle)
        self.assertIn("if (pt.open) ptOpen(null);", HTML)                          # HOME and Build close the dropdown: one under the strip at a time

    def test_portal_code_never_builds_html_from_data(self):
        block = HTML[HTML.index("// ====== PORTALS: Sports, Markets, Logistics, Economics ======"):HTML.index("function dockInit() {")]
        self.assertNotIn("innerHTML", block)
        self.assertNotIn("insertAdjacentHTML", block)
        self.assertNotIn("eval(", block)
        self.assertNotIn("window.open", block)
        self.assertIn("rel = 'noopener noreferrer'", block)
        self.assertIn("function ptSafeUrl", block)                                  # only http(s) links are ever made clickable

    def test_the_top_bar_has_three_slots_with_status_left_and_auto_save_right(self):
        bar = HTML[HTML.index('<header class="top-bar nx-bar">'):]
        bar = bar[:bar.index("</header>")]
        left, center, right = (bar.index('<div class="bar-%s">' % s) for s in ("left", "center", "right"))
        self.assertLess(left, center)
        self.assertLess(center, right)
        self.assertLess(left, bar.index('id="serverTelemetryIndicator"'))                    # the Python server status sits in the left slot
        self.assertLess(bar.index('id="serverTelemetryIndicator"'), center)
        self.assertLess(center, bar.index('id="mainSearchInput"'))                          # search and the tool buttons are in the middle
        self.assertLess(bar.index('id="mainSearchInput"'), right)
        self.assertLess(bar.index('id="promptVaultBtn"'), right)
        self.assertGreater(bar.index('id="archiveTelemetryIndicator"'), bar.index('id="notifWrap"'))     # Auto Save is the last thing in the right slot
        self.assertGreater(bar.index('id="archiveTelemetryIndicator"'), right)
        self.assertNotIn("margin-left: auto", bar)                                          # no more pushing things around with auto margins
        self.assertRegex(HTML, r"\.top-bar\.nx-bar \{ justify-content: space-between; \}")
        self.assertNotIn("padding-right: 360px", HTML)                                      # the reserve for the dock is measured, not guessed
        self.assertIn("--dock-w", HTML)
        self.assertEqual(HTML.count('id="serverTelemetryIndicator"'), 1)

    def test_each_hub_has_its_own_separate_chat_box(self):
        block = HTML[HTML.index("// ---- DOMAIN CHATS"):HTML.index("// ---- the dropdown itself ----")]
        self.assertIn('id="ptChats"', HTML)
        self.assertLess(HTML.index('id="dockPortalBody"'), HTML.index('id="ptChats"'))               # the chats sit below the body: at the bottom of the window
        self.assertGreater(HTML.index('id="ptChats"'), HTML.index('<div id="dockPortal"'))             # inside the portal window ...
        self.assertLess(HTML.index('id="ptChats"'), HTML.index('<div id="tokDialog"'))                # ... which ends before the next element
        self.assertNotIn('id="ptChats"', HTML[HTML.index('<div id="dockPerim"'):HTML.index('<div id="dockPortal"')])     # and the Perimeter window has no chat
        self.assertIn("Object.keys(PT_DEF).forEach(key => {", block)                                 # one instance per hub, each with its own box, log and input
        for needle in ("box.id = 'ptChat_' + key", "document.createElement('input')", "ptChatLog(key)", "{ portal: key, message: text }", "'api/portals/chat/reset', { portal: key }", "b.hidden = b.dataset.hub !== key"):
            self.assertIn(needle, block, needle)
        self.assertEqual(block.count("'api/portals/chat'"), 1)                                         # the one call carries the hub's own key, taken from the closure, never from the page state
        for forbidden in ("innerHTML", "insertAdjacentHTML", "eval(", "localStorage", "sessionStorage", "pt.open"):
            self.assertNotIn(forbidden, block, forbidden)                                              # replies are drawn as text; nothing is stored in the browser; the box never asks which hub is open
        self.assertIn("ptChatShow(key);", HTML)

    def test_every_hub_window_can_be_dragged_resized_expanded_minimised_and_closed(self):
        block = HTML[HTML.index("// ====== HUB WINDOWS"):HTML.index("// ====== SETTINGS READOUTS")]                 # the window code only: the next section is a different feature
        self.assertIn("const WIN_IDS = ['dockPortal', 'dockPerim', 'dockDesk'];", block)    # the four portals share dockPortal; the Perimeter and the engine desks have their own
        for needle in ("pointerdown", "pointermove", "pointerup", "pointercancel", "setPointerCapture", "function winClamp", "function winToggle", "function winUnmax", "function winReset", "'win-grip'",
                       "win-max-btn", "win-min-btn", "dblclick", "nxWin_"):
            self.assertIn(needle, block, needle)
        for needle in (".win-grip", ".dock-panel.win-max", ".dock-panel.win-min", "cursor: nwse-resize", "touch-action: none", ".dock-panel.win-dragging"):
            self.assertIn(needle, HTML, needle)
        # moving and sizing change geometry only: no window handler reads or writes the panel's content or the polling state
        for forbidden in ("pmRefresh", "pmGather", "dk.pmOpen", "pt.open =", "replaceChildren", "innerHTML"):
            self.assertNotIn(forbidden, block, forbidden)
        self.assertIn("WIN_IDS.forEach(winInit); winMeasureDock();", HTML)
        self.assertIn("winUnmax()", HTML)                                                   # Escape restores an expanded window before anything is closed
        self.assertIn("setInterval(set, 1500)", block)                                      # the dock width is re-measured even when the page is not painting

    def test_every_tab_the_page_draws_has_a_renderer(self):
        block = HTML[HTML.index("const PT_DEF"):HTML.index("const pt = {")]
        for portal, tabs in (("sports", ("broadcast", "edge", "players", "teams", "parlay")), ("markets", ("prob", "forecast")), ("logistics", ("cockpit", "stock", "flow", "delivery")), ("economics", ("macro", "model"))):
            for t in tabs:
                self.assertIn("['%s'," % t, block, t)
                self.assertIn("tab === '%s'" % t, HTML, "%s/%s has a tab button but no branch that draws it" % (portal, t)) if t not in ("model", "delivery", "forecast") else None
        for last in ("} else {\n        const kind = ptSelect", "} else {\n        const dl = ptBlank", "} else {\n        const days = ptBlank"):                       # the final tab of a portal is its else-branch
            self.assertIn(last.replace("\n", "\r\n") if "\r\n" in HTML else last, HTML)


if __name__ == "__main__":
    unittest.main(verbosity=1)
