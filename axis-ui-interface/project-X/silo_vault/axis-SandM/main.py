"""axis-SandM: the sales and marketing team. Starts the seven agents in priority order and reports who really came online.

Run from this folder:  python main.py          (health of every utility:  python health_report.py)
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# priority order: the governor first
ORDER = ["governor", "analyst", "strategist", "content_script_writer", "distributer_agent", "technical_agent", "visual_comercial_maker"]


def load_agent(silo):
    """-> an instance of the silo's agent class (the class in silos/<silo>/tool_request.py whose name ends in Agent)."""
    mod = importlib.import_module("silos.%s.tool_request" % silo)
    cls = next(getattr(mod, n) for n in dir(mod) if n.endswith("Agent") and isinstance(getattr(mod, n), type) and getattr(mod, n).__module__ == mod.__name__)
    return cls()


def run_system():
    """Start every agent. -> {silo: True (started) | error text}. One failing agent never stops the others."""
    import sandm_store as store
    result = {}
    halt = store.halted()
    for silo in ORDER:
        if halt:
            result[silo] = "not started: kill switch is on (%s)" % halt.get("reason")
            continue
        try:
            ok = load_agent(silo).start()
            result[silo] = True if ok in (None, True) else "started with problems"
            if result[silo] is True:
                store.beat(silo)
        except Exception as e:
            result[silo] = "%s: %s" % (type(e).__name__, e)
    return result


if __name__ == "__main__":
    res = run_system()
    bad = {k: v for k, v in res.items() if v is not True}
    print("\naxis-SandM: %d/%d agents online" % (len(res) - len(bad), len(res)))
    for k, v in bad.items():
        print("  NOT ONLINE: %s -> %s" % (k, v))
    sys.exit(1 if bad else 0)
