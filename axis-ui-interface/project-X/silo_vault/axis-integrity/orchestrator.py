"""orchestrator.py - axis-integrity's orchestrator: the AUDITOR on the orchestrator bus.

Every engine's orchestrator can report what happened inside its engine (core arming its lock, asking for a purge ...). NEXXUS writes each report into its own
hash-chained ledger and hands it to the auditor engine through the audit feed. This module takes the feed and writes every event into lib/auditor.py's
tamper-evident chain, and only THEN confirms to NEXXUS that it has them, so a crash in between means the events are offered again, not lost.

Run:  python orchestrator.py --once      (one round)      python orchestrator.py --serve      (keep listening)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


_WITNESS = {}


def ingest_once(link, auditor=None, witness=None):
    """Poll the audit feed, record the events, check them against reality (witness.py), confirm them. -> the number of events recorded.
    The witness keeps its state between calls (open purge requests ...), one per auditor."""
    if auditor is None:
        from lib.auditor import Auditor
        auditor = Auditor()
    if witness is None:
        from witness import Witness
        witness = _WITNESS.setdefault(id(auditor), Witness(auditor))
    polled = link.poll()
    if polled.get("status") != "success":
        return 0
    recorded = 0
    for item in polled.get("orders", []):
        if item.get("action") != "audit":
            continue
        for ev in item["events"]:
            auditor.log_event("%s:%s" % (ev["engine"], ev["kind"]), "#%d %s" % (ev["n"], ev["detail"]))
            recorded += 1
        witness.check(item["events"])                        # the findings are written into the same chain, right after the events they are about
        ack = link.audit_ack(item["upto"])                 # only after every event of this batch is in the chain
        if ack.get("status") != "success":
            raise RuntimeError("NEXXUS did not accept the confirmation: %s" % ack.get("message"))
    return recorded


if __name__ == "__main__":
    import time
    from nexxus_link import client
    link = client()
    if "--serve" in sys.argv:
        print("axis-integrity is listening to the audit feed (Ctrl+C to stop)")
        try:
            while True:
                n = ingest_once(link)
                if n:
                    print("recorded %d audit event(s)" % n)
                time.sleep(10)
        except KeyboardInterrupt:
            pass
    else:
        print("recorded %d audit event(s)" % ingest_once(link))
