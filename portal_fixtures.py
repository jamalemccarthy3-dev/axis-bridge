"""portal_fixtures.py - TEST SUPPORT ONLY. Schema-valid data sets that the tests write into a throwaway folder (NEXXUS_PORTAL_DATA) so the portal code has something to run on.

Nothing here is read by the product: the server only ever reads the owner's own portal_data/ files, and a file that says it is sample or placeholder data is rejected there. These fixtures
declare themselves as what they are (source: "unit-test fixture") and never touch portal_data/.
"""
import json
import os
import random

SOURCE = "unit-test fixture written by portal_fixtures.py, never shipped"


def _rets(n, mu, sd, seed):
    rnd = random.Random(seed)
    return [round(rnd.gauss(mu, sd), 5) for _ in range(n)]


def fixtures():
    """-> {data set name: document}. Deterministic."""
    rnd = random.Random(7)
    seasons = lambda base, n, slope: [{"season": 2017 + i, "pts": round(base + slope * i + rnd.uniform(-2.5, 2.5), 1), "ast": round(4 + rnd.uniform(-1, 1.5), 1), "reb": round(5 + rnd.uniform(-1.5, 1.5), 1)} for i in range(n)]  # noqa: E731
    kinds, stats = ["pallet", "container", "truck", "tote"], ["in transit", "in transit", "at dock", "delayed", "delivered", "held"]
    return {
        "ticker": {"source": SOURCE, "rows": [{"kind": "final", "text": "Alpha 101 - 96 Beta (final)"}, {"kind": "live", "text": "Gamma vs Delta, third quarter, 72 - 70"}, {"kind": "line", "text": "Alpha -2.5 / Beta +2.5"}]},
        "players": {"source": SOURCE, "players": [{"name": "Player One", "seasons": seasons(18, 7, 0.6)}, {"name": "Player Two", "seasons": seasons(24, 9, 0.2)}, {"name": "Player Three", "seasons": seasons(12, 5, 1.0)}]},
        "teams": {"source": SOURCE, "lower_is_better": ["turnovers", "points_allowed"], "teams": [
            {"name": "Team Alpha", "wins": 31, "games": 44, "rating": 1612, "stats": {"points": 109.4, "points_allowed": 101.2, "turnovers": 12.1, "rebounds": 44.0}},
            {"name": "Team Beta", "wins": 24, "games": 44, "rating": 1541, "stats": {"points": 104.8, "points_allowed": 103.9, "turnovers": 14.3, "rebounds": 46.2}},
            {"name": "Team Gamma", "wins": 20, "games": 44, "rating": 1503, "stats": {"points": 101.0, "points_allowed": 105.5, "turnovers": 13.0, "rebounds": 43.1}}]},
        "legs": {"source": SOURCE, "legs": [
            {"label": "Alpha to win", "odds": 1.62, "p": 0.66, "platform": "sportsbook"}, {"label": "Beta +4.5", "odds": 1.91, "p": 0.55, "platform": "sportsbook"}, {"label": "Over 211.5 total", "odds": 1.95, "p": 0.49, "platform": "sportsbook"},
            {"label": "Red on the wheel", "odds": 1.947, "p": 0.4865, "platform": "casino"}, {"label": "Gamma moneyline", "odds": 2.40, "p": 0.40, "platform": "sportsbook"}]},
        "series": {"source": SOURCE, "series": [{"symbol": "AAA", "start_price": 100.0, "returns": _rets(90, 0.0006, 0.011, 1)}, {"symbol": "BBB", "start_price": 42.5, "returns": _rets(90, -0.0002, 0.018, 2)},
                                                {"symbol": "CCC", "start_price": 250.0, "returns": _rets(90, 0.0010, 0.007, 3)}]},
        "assets": {"source": SOURCE, "on_hand": 58, "lead_time_demands": [40, 55, 60, 48, 70, 52, 66, 45, 58, 61],
                   "assets": [{"id": "A-%03d" % i, "name": "%s %d" % (kinds[i % 4], 100 + i), "kind": kinds[i % 4], "status": stats[i % 6], "location": ["Dock 3", "Route 9", "Hub East", "Yard B", "Gate 2"][i % 5], "eta": "day +%d" % (i % 5)} for i in range(14)]},
        "macro": {"source": SOURCE, "series": [{"name": "Price index", "unit": "index", "values": [round(100 + i * 0.35 + rnd.uniform(-0.6, 0.6), 2) for i in range(28)]},
                                              {"name": "Output index", "unit": "index", "values": [round(100 + i * 0.5 + rnd.uniform(-1.4, 1.4), 2) for i in range(28)]},
                                              {"name": "Unemployment", "unit": "%", "values": [round(5.2 - i * 0.04 + rnd.uniform(-0.15, 0.15), 2) for i in range(28)]}]},
    }


def write(directory, root=None):
    """Write every fixture into `directory`, plus the real field catalog (hub_catalog.json is the owner's real list of real tools, not data)."""
    os.makedirs(directory, exist_ok=True)
    for name, doc in fixtures().items():
        with open(os.path.join(directory, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(doc, f)
    if root:
        src = os.path.join(root, "portal_data", "hub_catalog.json")
        with open(src, encoding="utf-8") as f, open(os.path.join(directory, "hub_catalog.json"), "w", encoding="utf-8") as g:
            g.write(f.read())
