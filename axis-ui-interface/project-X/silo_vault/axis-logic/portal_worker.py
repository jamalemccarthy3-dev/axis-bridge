# portal_worker.py - the backend compute behind the four NEXXUS portals (Sports, Markets, Logistics, Economics).
#
# One request in, one answer out: `python -I portal_worker.py` reads {"op": "...", "args": {...}} as JSON on stdin and prints one JSON object. The NEXXUS server
# (nexxus/portals.py) runs it in a throwaway process, so this folder's generic module names (markets, pipeline, probability) never touch the server.
# Every op reports estimates with their uncertainty. Nothing here places a bet, trades, orders or ships anything.
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "lib"), os.path.join(HERE, "src", "silo_manager")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

import economics  # noqa: E402
import logistics  # noqa: E402
import markets  # noqa: E402
import probability as P  # noqa: E402


def _load_engine(folder, module, cls):
    import importlib.util
    spec = importlib.util.spec_from_file_location("portal_" + module, os.path.join(HERE, folder, module + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, cls)()


def _num_list(x, name, minimum=1, maximum=5000):
    if not isinstance(x, list) or len(x) < minimum or len(x) > maximum:
        raise ValueError("%s must be a list of %d to %d numbers" % (name, minimum, maximum))
    return [float(v) for v in x]


# ---------------------------------------------------------------- sports
def sports_evaluate(a):
    return _load_engine("sports", "sports", "SportsEngine").calculate({"wins": int(a["wins"]), "games": int(a["games"]), "decimal_odds": _num_list(a["decimal_odds"], "decimal_odds", 2, 30),
                                                                      "outcome_index": int(a.get("outcome_index", 0))})


def sports_compare(a):
    """Side-by-side team matrix. teams: [{name, wins, games, rating?, stats?: {label: number}}]; `lower_is_better` names the stats where less wins."""
    teams = a.get("teams")
    if not isinstance(teams, list) or not 2 <= len(teams) <= 6:
        raise ValueError("compare 2 to 6 teams")
    lower = set(a.get("lower_is_better") or [])
    rows = []
    for t in teams:
        w, g = int(t["wins"]), int(t["games"])
        if g <= 0 or w < 0 or w > g:
            raise ValueError("%s: games must be positive and 0 <= wins <= games" % t.get("name", "team"))
        lo, hi = P.wilson_interval(w, g)
        rows.append({"name": str(t.get("name", "?"))[:40], "win_rate": w / g, "low": lo, "high": hi, "n": g, "rating": t.get("rating"), "stats": dict(t.get("stats") or {})})
    labels = []
    for r in rows:
        for k in r["stats"]:
            if k not in labels:
                labels.append(k)
    leaders = {}
    for k in labels:
        vals = [(r["stats"].get(k), r["name"]) for r in rows if isinstance(r["stats"].get(k), (int, float))]
        if len(vals) >= 2:
            pick = min(vals) if k in lower else max(vals)
            tie = [v for v in vals if v[0] == pick[0]]
            leaders[k] = None if len(tie) > 1 else pick[1]
    head = None
    if len(rows) == 2 and all(isinstance(r["rating"], (int, float)) for r in rows):
        _, _, exp = markets.elo_update(float(rows[0]["rating"]), float(rows[1]["rating"]), 0.5)
        head = {"first": rows[0]["name"], "expected_score_first": exp}
    # a win-rate gap is only reported as real when the two Wilson intervals do not overlap
    separated = len(rows) == 2 and (rows[0]["low"] > rows[1]["high"] or rows[1]["low"] > rows[0]["high"])
    return {"teams": rows, "stat_labels": labels, "leaders": leaders, "head_to_head": head, "records_clearly_different": bool(separated)}


def sports_player(a):
    """Lifetime or single-season stat query over rows the owner supplied. players: [{name, seasons: [{season, <stat>: number...}]}]."""
    players, name, stat, mode = a.get("players") or [], str(a.get("player") or "").strip().lower(), str(a.get("stat") or ""), str(a.get("mode") or "career")
    p = next((x for x in players if str(x.get("name", "")).lower() == name), None)
    if p is None:
        raise ValueError("no player named %r in the data" % a.get("player"))
    seasons = [s for s in p.get("seasons", []) if isinstance(s.get(stat), (int, float))]
    if not seasons:
        raise ValueError("%s has no %r figures" % (p.get("name"), stat))
    vals = np.asarray([float(s[stat]) for s in seasons])
    best = max(seasons, key=lambda s: s[stat])
    out = {"player": p.get("name"), "stat": stat, "seasons": [{"season": s.get("season"), "value": s[stat]} for s in seasons], "best_season": {"season": best.get("season"), "value": best[stat]}}
    if mode == "season":
        want = a.get("season")
        row = next((s for s in seasons if str(s.get("season")) == str(want)), None)
        if row is None:
            raise ValueError("no %s season for %s" % (want, p.get("name")))
        out["value"] = row[stat]
        out["rank_among_own_seasons"] = 1 + sum(1 for s in seasons if s[stat] > row[stat])
    else:
        out.update({"career_total": float(vals.sum()), "per_season": float(vals.mean()), "seasons_counted": int(vals.size)})
        if vals.size >= 4:
            lo, hi = P.bootstrap_interval(vals, seed=0)
            out["per_season_low"], out["per_season_high"] = lo, hi
    return out


def sports_parlay(a):
    """Filter and price a parlay. legs: [{label, odds, platform?, p?}] (odds decimal; p = your own win probability for the leg). Nothing is staked."""
    legs = a.get("legs")
    if not isinstance(legs, list) or not 1 <= len(legs) <= 30:
        raise ValueError("give 1 to 30 legs")
    allowed = set(a.get("platforms") or [])
    lo_o, hi_o = float(a.get("min_odds", 1.0)), float(a.get("max_odds", 1000.0))
    min_edge, max_legs = float(a.get("min_edge", -1.0)), int(a.get("max_legs", 8))
    kept, dropped = [], []
    for g in legs:
        o = float(g["odds"])
        if not math.isfinite(o) or o <= 1.0:
            raise ValueError("%s: decimal odds must be greater than 1.0" % g.get("label", "leg"))
        why = None
        if allowed and g.get("platform") not in allowed:
            why = "platform %s filtered out" % (g.get("platform") or "unknown")
        elif not lo_o <= o <= hi_o:
            why = "odds %.2f outside %.2f to %.2f" % (o, lo_o, hi_o)
        elif isinstance(g.get("p"), (int, float)) and (g["p"] - 1.0 / o) < min_edge:
            why = "edge %.3f below %.3f" % (g["p"] - 1.0 / o, min_edge)
        (dropped if why else kept).append(dict(g, why=why) if why else g)
    if len(kept) > max_legs:
        for g in kept[max_legs:]:
            dropped.append(dict(g, why="over the %d-leg limit" % max_legs))
        kept = kept[:max_legs]
    res = {"kept": kept, "dropped": dropped, "legs": len(kept)}
    if kept:
        combined = float(np.prod([float(g["odds"]) for g in kept]))
        res["combined_odds"], res["combined_implied_probability"] = combined, 1.0 / combined
        ps = [g.get("p") for g in kept]
        if all(isinstance(p, (int, float)) for p in ps):
            mp = float(np.prod(ps))
            res["model_probability"] = mp
            res["edge"] = markets.edge(mp, 1.0 / combined)
            res["kelly_fraction"] = markets.kelly_fraction(mp, combined)
            res["note"] = "legs are treated as independent; correlated legs (same game) make this number wrong"
        else:
            res["note"] = "add your own probability per leg to see the edge; odds alone only show what the book implies"
    return res


# ---------------------------------------------------------------- markets
def markets_analyze(a):
    data = {"returns": _num_list(a["returns"], "returns", 2)}
    if a.get("prices"):
        data["prices"] = _num_list(a["prices"], "prices", 2)
    return _load_engine("stocks", "stocks", "StocksEngine").calculate(data)


def markets_forecast(a):
    """Bootstrap cone: resample the supplied daily returns to price paths. The cone is what the PAST distribution of returns would give, not a prediction."""
    r = np.asarray(_num_list(a["returns"], "returns", 10), dtype=float)
    start, days, paths = float(a.get("start_price", 100.0)), max(1, min(int(a.get("days", 60)), 252)), max(200, min(int(a.get("paths", 1000)), 3000))
    if start <= 0:
        raise ValueError("start_price must be positive")
    rng = np.random.default_rng(int(a.get("seed", 0)))
    steps = rng.choice(r, size=(paths, days), replace=True)
    walk = start * np.cumprod(1.0 + steps, axis=1)
    qs = [5, 25, 50, 75, 95]
    bands = {str(q): [float(x) for x in np.percentile(walk, q, axis=0)] for q in qs}
    return {"start_price": start, "days": days, "paths": paths, "bands": bands, "probability_above_start": float((walk[:, -1] > start).mean()),
            "note": "resampled from %d past returns: a spread of what history allows, not a forecast" % r.size}


# ---------------------------------------------------------------- logistics
def logistics_stockout(a):
    return markets.stockout_signal(_num_list(a["lead_time_demands"], "lead_time_demands", 2), float(a["on_hand"]))


def logistics_queue(a):
    out = markets.queue_metrics(a["arrival_rate"], a["service_rate"], int(a.get("servers", 1)))
    return out


def logistics_eoq(a):
    return logistics.eoq(a["annual_demand"], a["order_cost"], a["holding_cost"])


def logistics_reorder(a):
    return logistics.reorder_point(a["daily_demand"], a["lead_time_days"], a.get("daily_demand_sd", 0.0))


def logistics_ontime(a):
    return logistics.on_time_rate(a["delivered"], a["on_time"])


def logistics_fulfillment_test(a):
    """Did a change to fulfilment (variant) really move the on-time rate? Same significance test the ecom engine uses."""
    c, v = a["control"], a["variant"]
    return markets.ab_test(int(c["on_time"]), int(c["delivered"]), int(v["on_time"]), int(v["delivered"]))


# ---------------------------------------------------------------- economics
def economics_model(a):
    kind = str(a.get("kind"))
    if kind == "cagr":
        return {"cagr": economics.cagr(a["start"], a["end"], a["years"])}
    if kind == "real_rate":
        return {"real_rate": economics.real_rate(a["nominal"], a["inflation"])}
    if kind == "future_value":
        path = economics.future_value(a["principal"], a["rate"], a.get("years", 10), a.get("contribution", 0.0), a.get("per_year", 12))
        return {"balances": path, "final": path[-1], "contributed": float(a["principal"]) + float(a.get("contribution", 0.0)) * int(a.get("per_year", 12)) * int(a.get("years", 10))}
    if kind == "npv":
        flows = _num_list(a["cash_flows"], "cash_flows", 2, 200)
        return {"npv": economics.npv(a["rate"], flows), "irr": economics.irr(flows)}
    if kind == "loan":
        return economics.loan(a["principal"], a["rate"], a["years"], a.get("per_year", 12))
    if kind == "trend":
        return economics.trend(_num_list(a["values"], "values", 5, 2000), a.get("horizon", 4))
    if kind == "inflation_adjust":
        return {"adjusted": economics.inflation_adjust(a["amount"], a["from_index"], a["to_index"])}
    raise ValueError("unknown economics model %r" % kind)


def hub_search(a):
    """The hub search lives in axis-core (hub_search.py); it is loaded by path under its own name so axis-core's other module names never enter this process."""
    import importlib.util
    path = os.path.join(os.path.dirname(HERE), "axis-core", "hub_search.py")
    spec = importlib.util.spec_from_file_location("axis_core_hub_search", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.search(a.get("entries") or [], str(a.get("query") or "")[:120], a.get("kind") or None, int(a.get("limit", 24)))


OPS = {
    "hub.search": hub_search,
    "sports.evaluate": sports_evaluate, "sports.compare": sports_compare, "sports.player": sports_player, "sports.parlay": sports_parlay,
    "markets.analyze": markets_analyze, "markets.forecast": markets_forecast,
    "logistics.stockout": logistics_stockout, "logistics.queue": logistics_queue, "logistics.eoq": logistics_eoq, "logistics.reorder": logistics_reorder,
    "logistics.ontime": logistics_ontime, "logistics.fulfillment_test": logistics_fulfillment_test,
    "economics.model": economics_model,
}


def _clean(x):
    """JSON that browsers accept: numpy types become plain ones, NaN and infinity become null."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def main():
    try:
        req = json.loads(sys.stdin.read())
        fn = OPS.get(req.get("op"))
        if fn is None:
            raise ValueError("unknown op %r" % req.get("op"))
        out = {"status": "success", "result": _clean(fn(req.get("args") or {}))}
    except KeyError as e:
        out = {"status": "error", "message": "missing field %s" % e}
    except (ValueError, TypeError, ZeroDivisionError, json.JSONDecodeError) as e:
        out = {"status": "error", "message": str(e)}
    sys.stdout.write(json.dumps(out, allow_nan=False))


if __name__ == "__main__":
    main()
