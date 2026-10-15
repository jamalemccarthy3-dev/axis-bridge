"""portal_schemas.py - the real data contracts of the four portals: what each data set must look like, what each calculator takes, and the live-state block every hub prompt carries.

This module contains NO data and no example values. A data set is the owner's own, in portal_data/<name>.json, and it must:
  * say where it came from ("source", required: the provenance that makes it authentic),
  * follow the schema below, row by row,
  * not be sample, placeholder, demo or mock data: a file that says so (or whose names say so) is rejected, so fake data cannot creep back in and feed the models and validation layers.
A missing file is simply "not loaded": the portals, the hub chats and their prompts say that plainly and never fill the gap.
"""
import math
import re

PLACEHOLDER = re.compile(r"\b(sample|placeholder|lorem|dummy|mock|fake|demo|example)\b", re.I)
MAX_ERRORS = 12


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _text(v, n):
    return isinstance(v, str) and 0 < len(v.strip()) <= n


# field kinds: (checker, human description)
_KINDS = {
    "text": (lambda v, a: _text(v, a or 120), "text"),
    "int>=0": (lambda v, a: _int(v) and v >= 0, "whole number >= 0"),
    "int>0": (lambda v, a: _int(v) and v > 0, "whole number > 0"),
    "year": (lambda v, a: _int(v) and 1800 <= v <= 2200, "year"),
    "num": (lambda v, a: _num(v), "number"),
    "odds": (lambda v, a: _num(v) and v > 1.0, "decimal odds > 1"),
    "prob": (lambda v, a: _num(v) and 0.0 < v < 1.0, "probability between 0 and 1"),
    "price": (lambda v, a: _num(v) and v > 0, "number > 0"),
    "num>=0": (lambda v, a: _num(v) and v >= 0, "number >= 0"),
    "enum": (lambda v, a: v in a, "one of: %s"),
    "stats": (lambda v, a: isinstance(v, dict) and v and all(_text(k, 60) and _num(x) for k, x in v.items()), "object of name: number"),
    "list_text": (lambda v, a: isinstance(v, list) and all(_text(x, 60) for x in v), "list of text"),
    "returns": (lambda v, a: isinstance(v, list) and 10 <= len(v) <= 5000 and all(_num(x) and x > -1.0 for x in v), "list of 10 to 5000 daily returns, each > -1 (0.01 = +1%)"),
    "values": (lambda v, a: isinstance(v, list) and 5 <= len(v) <= 2000 and all(_num(x) for x in v), "list of 5 to 2000 numbers, oldest first"),
    "demands": (lambda v, a: isinstance(v, list) and 2 <= len(v) <= 2000 and all(_num(x) and x >= 0 for x in v), "list of 2 or more demand totals over past lead times, each >= 0"),
    "seasons": (lambda v, a: isinstance(v, list) and v, "list of season rows"),
}

# per data set: the list that holds the rows, the row fields (kind, required, argument), and optional top-level fields
SCHEMAS = {
    "ticker": {"list": "rows", "max": 500, "what": "the lines the Sports broadcast ticker scrolls", "row": {"kind": ("enum", True, ("final", "live", "line", "news")), "text": ("text", True, 240), "at": ("text", False, 40)}, "top": {}},
    "players": {"list": "players", "max": 5000, "what": "players and their season-by-season numbers", "row": {"name": ("text", True, 80), "seasons": ("seasons", True, None)}, "top": {}},
    "teams": {"list": "teams", "max": 500, "what": "teams with their record and stats", "row": {"name": ("text", True, 80), "wins": ("int>=0", True, None), "games": ("int>0", True, None), "rating": ("num", False, None), "stats": ("stats", False, None)},
              "top": {"lower_is_better": ("list_text", False, None)}},
    "legs": {"list": "legs", "max": 500, "what": "the sportsbook and casino legs you want filtered and priced", "row": {"label": ("text", True, 120), "odds": ("odds", True, None), "platform": ("text", True, 60), "p": ("prob", False, None)}, "top": {}},
    "series": {"list": "series", "max": 200, "what": "price histories as daily returns", "row": {"symbol": ("text", True, 40), "start_price": ("price", True, None), "returns": ("returns", True, None)}, "top": {}},
    "assets": {"list": "assets", "max": 20000, "what": "the assets and shipments to track", "row": {"id": ("text", True, 80), "name": ("text", True, 120), "kind": ("text", True, 60), "status": ("text", True, 60), "location": ("text", True, 120), "eta": ("text", False, 60)},
               "top": {"lead_time_demands": ("demands", False, None), "on_hand": ("num>=0", False, None)}},
    "macro": {"list": "series", "max": 200, "what": "macro-economic series", "row": {"name": ("text", True, 120), "unit": ("text", True, 40), "values": ("values", True, None)}, "top": {}},
}

# the arguments of every calculator, exactly as portal_worker.py reads them (a test keeps this list complete)
OP_ARGS = {
    "sports.evaluate": "wins:int, games:int, decimal_odds:[number>1, 2 or more], outcome_index:int",
    "sports.compare": "teams:[{name, wins:int, games:int, rating?:number, stats?:{name:number}}] (2 to 6), lower_is_better?:[text]",
    "sports.player": "players:[{name, seasons:[{season:year, <stat>:number}]}], player:text, stat:text, mode:career|season, season?:year",
    "sports.parlay": "legs:[{label, odds>1, platform?, p?:0..1}], platforms?:[text], min_odds?, max_odds?, min_edge?, max_legs?",
    "markets.analyze": "returns:[daily returns, 2 or more], prices?:[number>0]",
    "markets.forecast": "returns:[daily returns, 10 or more], start_price:number>0, days:1..252, paths?:200..3000, seed?:int",
    "logistics.stockout": "lead_time_demands:[number>=0, 2 or more], on_hand:number",
    "logistics.queue": "arrival_rate:number>0, service_rate:number>0, servers:int>=1",
    "logistics.eoq": "annual_demand:number>0, order_cost:number>0, holding_cost:number>0",
    "logistics.reorder": "daily_demand:number>0, lead_time_days:number>0, daily_demand_sd?:number>=0",
    "logistics.ontime": "delivered:int>0, on_time:int (<= delivered)",
    "logistics.fulfillment_test": "control:{delivered, on_time}, variant:{delivered, on_time}",
    "economics.model": "kind:cagr|real_rate|future_value|npv|loan|trend|inflation_adjust plus that kind's fields (cagr: start,end,years; real_rate: nominal,inflation; future_value: principal,rate,years,contribution,per_year; "
                       "npv: rate,cash_flows; loan: principal,rate,years,per_year; trend: values,horizon; inflation_adjust: amount,from_index,to_index); rates are fractions (0.05 = 5%)",
    "hub.search": "portal:text, query:text, kind?:api|database|calculator|feed|platform|library, limit?:int",
}


def _kind_text(kind, arg):
    desc = _KINDS[kind][1]
    return desc % ", ".join(arg) if kind == "enum" else desc


def describe(name):
    """The contract of one data set as plain text (field names and kinds only: never example values)."""
    s = SCHEMAS[name]
    fields = ", ".join("%s%s: %s" % (f, "" if req else "?", _kind_text(k, a)) for f, (k, req, a) in s["row"].items())
    top = "".join(", %s?: %s" % (f, _kind_text(k, a)) for f, (k, _r, a) in s["top"].items())
    return ("portal_data/%s.json holds %s: {source: text (where this data came from, required), as_of?: text, %s: [ {%s} ] (1 to %d rows)%s}. It must be real data: sample, placeholder, demo or mock data is rejected."
            % (name, s["what"], s["list"], fields, s["max"], top))


def _placeholder_hits(doc, s):
    hits = []
    if isinstance(doc.get("source"), str) and PLACEHOLDER.search(doc["source"]):
        hits.append("source says %r" % PLACEHOLDER.search(doc["source"]).group(0))
    for i, row in enumerate(doc.get(s["list"], []) if isinstance(doc.get(s["list"]), list) else []):
        if isinstance(row, dict):
            for f in ("name", "label", "symbol", "id", "text"):
                if isinstance(row.get(f), str) and PLACEHOLDER.search(row[f]):
                    hits.append("%s[%d].%s says %r" % (s["list"], i, f, PLACEHOLDER.search(row[f]).group(0)))
    return hits


def validate(name, doc):
    """-> list of problems (empty = valid). Checks the shape, every row, provenance, and that the data does not call itself sample or placeholder."""
    if name not in SCHEMAS:
        return ["unknown data set %r" % name]
    s, errs = SCHEMAS[name], []
    if not isinstance(doc, dict):
        return ["the file must hold one JSON object"]
    if doc.get("sample") is True:
        errs.append("marked sample: sample data is not accepted here")
    if not _text(doc.get("source"), 200):
        errs.append("source is required: say where this data came from")
    errs += ["looks like placeholder data: " + h for h in _placeholder_hits(doc, s)]
    rows = doc.get(s["list"])
    if not isinstance(rows, list) or not 1 <= len(rows) <= s["max"]:
        errs.append("%s must be a list of 1 to %d rows" % (s["list"], s["max"]))
        return errs[:MAX_ERRORS]
    for f, (k, req, a) in s["top"].items():
        if f in doc and not _KINDS[k][0](doc[f], a):
            errs.append("%s must be %s" % (f, _kind_text(k, a)))
    seen = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errs.append("%s[%d] must be an object" % (s["list"], i))
            continue
        for f, (k, req, a) in s["row"].items():
            if f not in row:
                if req:
                    errs.append("%s[%d].%s is required" % (s["list"], i, f))
            elif not _KINDS[k][0](row[f], a):
                errs.append("%s[%d].%s must be %s" % (s["list"], i, f, _kind_text(k, a)))
        errs += _rules(name, i, row, seen)
        if len(errs) >= MAX_ERRORS:
            break
    return errs[:MAX_ERRORS]


def _rules(name, i, row, seen):
    """Cross-field rules a kind check cannot express."""
    out = []
    if name == "teams" and _int(row.get("wins")) and _int(row.get("games")) and row["wins"] > row["games"]:
        out.append("teams[%d]: wins cannot exceed games" % i)
    if name in ("assets", "players", "teams", "series") and isinstance(row.get({"assets": "id", "players": "name", "teams": "name", "series": "symbol"}[name]), str):
        key = row[{"assets": "id", "players": "name", "teams": "name", "series": "symbol"}[name]].strip().lower()
        if key in seen:
            out.append("%s[%d]: %r appears twice" % (name, i, key))
        seen.add(key)
    if name == "players" and isinstance(row.get("seasons"), list):
        for j, se in enumerate(row["seasons"]):
            if not isinstance(se, dict) or not _int(se.get("season")) or not 1800 <= se["season"] <= 2200:
                out.append("players[%d].seasons[%d].season must be a year" % (i, j))
            elif not any(_num(v) for k, v in se.items() if k != "season"):
                out.append("players[%d].seasons[%d] has no numbers" % (i, j))
            elif any(not _num(v) for k, v in se.items() if k != "season"):
                out.append("players[%d].seasons[%d]: every stat must be a number" % (i, j))
    return out


def summary(name, doc):
    return {"row_count": len(doc.get(SCHEMAS[name]["list"], []))}


def prompt_block(state):
    """The live state of one hub as the text its model is given every turn: what is loaded (with provenance), what is not, the exact calculator arguments, and the rule that follows from them."""
    lines = ["LIVE STATE of this system, read just now (the only ground truth you have):"]
    for d in state["data"]:
        if d["status"] == "loaded":
            lines.append("- data set %s: LOADED, %d rows, source: %s" % (d["name"], d["row_count"], d["source"]))
        elif d["status"] == "invalid":
            lines.append("- data set %s: file present but REJECTED (%s)" % (d["name"], "; ".join(d["errors"][:2])))
        else:
            lines.append("- data set %s: NOT LOADED" % d["name"])
    lines.append("- calculators the user can run in this hub's window: " + "; ".join("%s(%s)" % (o["op"], o["args"]) for o in state["ops"]))
    lines.append("- field catalog: %d tool and data-source entries (an editorial list, not live)%s" % (state["catalog_entries"], (", added to this hub: " + ", ".join(state["mounted"])) if state["mounted"] else ""))
    lines.append("RULE: you have no figures except the loaded data sets, the user's own numbers and the tool results shown to you. If a data set is NOT LOADED, say there is no data and what would be needed; "
                 "never invent a score, price, rate, row, name or statistic, and never present an example as if it were real.")
    return "\n".join(lines)
