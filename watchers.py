"""watchers.py - NEXXUS watcher bots: they WATCH for signs of malicious intent and TELL the operator. They never act.

Conduct rules, enforced in code and in test_watchers.py:
  * Read-only. A watcher reads a log or a store and returns findings. This module imports nothing that can end a process, change a file outside its own findings log, or block anyone
    (no subprocess, signal, shutil, socket or kill), and the test fails if that ever changes.
  * Observe and flag, never kill or block. A finding is a notification with the evidence and a suggestion. What happens next is the operator's decision (Hard Lock, Quarantine and the rate
    limits stay the operator's own switches in perimeter.py and the relay).
  * Intent, not people. Rules look for patterns (floods, schema probing, repeated refusals), never for who someone is; they keep no names, no IP addresses and no content. Findings hold counts
    and short random install ids only.
  * Quiet by default. Each finding fires once per cooldown (1 hour) per rule and subject, so a long attack does not bury the operator.

The bots: relay_flood, id_churn, reject_rate (telemetry); operator_probing (operator_scope refusals); capture_probing (refused capture attempts).
Thresholds are environment variables (NEXXUS_WATCH_FLOOD, _CHURN, _REJECT_RATIO, _OPERATOR_REFUSALS, _CAPTURE_REFUSALS). Standard library only.
"""
import json
import os
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS_PATH = os.path.join(HERE, "nexxus_data", "telemetry", "sandbox_events.jsonl")
PULL_STATS_PATH = os.path.join(HERE, "nexxus_data", "telemetry", "pull_stats.jsonl")
OPERATOR_AUDIT = os.path.join(HERE, "logs", "operator_audit.jsonl")
CAPTURE_AUDIT = os.path.join(HERE, "logs", "capture_audit.jsonl")
FINDINGS_PATH = os.path.join(HERE, "nexxus_data", "state", "watch_findings.jsonl")
COOLDOWN = 3600
_LOCK = threading.RLock()


def _num(name, default, cast=int):
    try:
        return cast(os.environ.get(name, default))
    except (TypeError, ValueError):
        return cast(default)


def _read_jsonl(path, since):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                t = d.get("t", d.get("ts", 0))
                if isinstance(t, (int, float)) and t >= since:
                    out.append(d)
    except OSError:
        pass
    return out


def _finding(rule, severity, subject, summary, evidence):
    return {"rule": rule, "severity": severity, "subject": subject, "summary": summary, "evidence": evidence,
            "suggestion": "Review it. Nothing was blocked or stopped; any action is yours to take."}


def relay_flood(now):
    limit = _num("NEXXUS_WATCH_FLOOD", 120)
    counts = {}
    for e in _read_jsonl(EVENTS_PATH, now - 3600):
        counts[e.get("i", "?")] = counts.get(e.get("i", "?"), 0) + 1
    return [_finding("relay_flood", "warn", i[:8], "One install sent %d events in an hour (normal is a handful)." % n, {"install": i[:8], "events_last_hour": n, "threshold": limit})
            for i, n in counts.items() if n > limit]


def id_churn(now):
    limit = _num("NEXXUS_WATCH_CHURN", 200)
    first = {}
    for e in _read_jsonl(EVENTS_PATH, now - 86400):
        i = e.get("i")
        if i and (i not in first or e["t"] < first[i]):
            first[i] = e["t"]
    new = sum(1 for t in first.values() if t >= now - 600)
    return [_finding("id_churn", "warn", "installs", "%d brand-new install ids appeared in 10 minutes (possible fake-install spam)." % new, {"new_ids_10min": new, "threshold": limit})] if new > limit else []


def reject_rate(now):
    ratio = _num("NEXXUS_WATCH_REJECT_RATIO", 0.3, float)
    rec = dropped = 0
    for p in _read_jsonl(PULL_STATS_PATH, now - 3600):
        rec += int(p.get("received", 0))
        dropped += int(p.get("dropped", 0))
    if rec >= 50 and dropped / rec > ratio:
        return [_finding("reject_rate", "alert", "relay", "%d%% of events pulled in the last hour failed the schema (someone may be probing the relay)." % round(100 * dropped / rec),
                         {"received": rec, "dropped": dropped, "threshold_ratio": ratio})]
    return []


def operator_probing(now):
    limit = _num("NEXXUS_WATCH_OPERATOR_REFUSALS", 10)
    n = sum(1 for e in _read_jsonl(OPERATOR_AUDIT, now - 600) if e.get("allowed") is False and e.get("action") not in ("grant", "revoke"))
    return [_finding("operator_probing", "alert", "operator-mode", "%d operator-mode requests were refused in 10 minutes (paths outside granted folders)." % n, {"refused_10min": n, "threshold": limit})] if n >= limit else []


def capture_probing(now):
    limit = _num("NEXXUS_WATCH_CAPTURE_REFUSALS", 5)
    n = sum(1 for e in _read_jsonl(CAPTURE_AUDIT, now - 600) if e.get("allowed") is False)
    return [_finding("capture_probing", "alert", "capture", "%d screen or camera capture attempts were refused in 10 minutes (capture is switched off)." % n, {"refused_10min": n, "threshold": limit})] if n >= limit else []


BOTS = (relay_flood, id_churn, reject_rate, operator_probing, capture_probing)


def _recent_keys(now):
    return {(f["rule"], f["subject"]) for f in _read_jsonl(FINDINGS_PATH, now - COOLDOWN)}


def scan(now=None, notifier=None):
    """Run every bot once. New findings (outside their cooldown) are logged and passed to `notifier(finding)`. -> the list of new findings."""
    now = time.time() if now is None else now
    new = []
    with _LOCK:
        seen = _recent_keys(now)
        for bot in BOTS:
            try:
                found = bot(now)
            except Exception:
                continue          # a broken bot must never take anything else down
            for f in found:
                if (f["rule"], f["subject"]) in seen:
                    continue
                f["t"] = int(now)
                new.append(f)
        if new:
            os.makedirs(os.path.dirname(FINDINGS_PATH), exist_ok=True)
            with open(FINDINGS_PATH, "a", encoding="utf-8") as fh:
                for f in new:
                    fh.write(json.dumps(f) + "\n")
    for f in new:
        if notifier:
            try:
                notifier(f)
            except Exception:
                pass
    return new


def recent(hours=24, now=None):
    now = time.time() if now is None else now
    return _read_jsonl(FINDINGS_PATH, now - hours * 3600)


_run = {"thread": None, "stop": threading.Event()}


def start(every=60, notifier=None):
    if _run["thread"] and _run["thread"].is_alive():
        return False

    def loop():
        while not _run["stop"].wait(every):
            scan(notifier=notifier)
    _run["stop"].clear()
    _run["thread"] = threading.Thread(target=loop, name="watchers", daemon=True)
    _run["thread"].start()
    return True


if __name__ == "__main__":
    for f in scan():
        print(json.dumps(f))
    print("findings in the last 24 hours:", len(recent()))
