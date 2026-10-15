# main.py - Sovereign Startup Architecture
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.append(HERE)

REQUIRED = [("security", "shield"), ("security", "sentry"), ("security", "mirror_box"), ("security", "freeze_all"), ("bridge", "bridge"), ("bridge", "processor"),
            ("bridge", "deliverer"), ("bridge", "purge_engine"), ("auditor_interface", "auditor_settings"), ("auditor_interface", "validator"), ("auditor_interface", "master_director")]


def boots_district():
    """Brings the district up for real and says what it found: the data folder is writable, every layer module loads, the audit ledger verifies, and the engine is neither halted
    nor in LOCKDOWN. -> {"ready": bool, "checks": {name: "ok" | problem}}. Nothing is printed as 'ready' unless every check passed."""
    from lib.layers import load
    import integrity_store as store
    checks = {}
    try:
        probe = store.path("boot_probe.json")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("{}")
        os.remove(probe)
        checks["data_folder"] = "ok"
    except OSError as e:
        checks["data_folder"] = "not writable: %s" % e
    for layer, mod in REQUIRED:
        try:
            load(layer if layer == "auditor_interface" else "src/" + layer, mod)
            checks["%s/%s" % (layer, mod)] = "ok"
        except Exception as e:                                               # noqa: BLE001 - a module that will not load is a boot finding, not a crash
            checks["%s/%s" % (layer, mod)] = "%s: %s" % (type(e).__name__, str(e)[:80])
    try:
        from lib.auditor import Auditor
        ok, detail = Auditor().verify()
        checks["ledger"] = "ok" if ok else "ledger broken at entry %s" % detail
    except Exception as e:                                                   # noqa: BLE001
        checks["ledger"] = "%s: %s" % (type(e).__name__, e)
    checks["not_halted"] = "ok" if not (store.read_json("halt.json", {}) or {}).get("halted") else "the fail-safe halt is set"
    checks["mode"] = "ok" if (store.read_json("settings.json", {}) or {}).get("mode", "LIVE") != "LOCKDOWN" else "the auditor is in LOCKDOWN"
    return {"ready": all(v == "ok" for v in checks.values()), "checks": checks}


def main():
    report = boots_district()
    for name, state in report["checks"].items():
        print("  %-34s %s" % (name, state))
    print("District ready." if report["ready"] else "District NOT ready: see the checks above.")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
