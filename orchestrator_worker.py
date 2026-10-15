"""orchestrator_worker.py - the loop an engine's ORCHESTRATOR runs: ask NEXXUS what to do, do it, report back.

    run_once(link, build=my_build, review=my_review)
      ack     a new order is acknowledged
      build   my_build(order) -> path of the artifact (the orchestrator builds, then reports; NEXXUS hashes the file itself)
      review  my_review(order) -> (verdict "pass"|"fail", findings, artifact_sha256)   (QC reviewer engines only)
A failing handler never stops the loop and never reports success: the error is returned and the order stays where it was.
`serve(link, ..., interval=15)` repeats run_once forever (Ctrl+C to stop). Standard library only.
"""
import time


def run_once(link, build=None, review=None):
    """-> list of {order, action, result}. Does at most one step per order per call, so every step is visible and ordered."""
    polled = link.poll()
    if polled.get("status") != "success":
        return [{"order": None, "action": "poll", "result": polled}]
    done = []
    for o in polled.get("orders", []):
        act, oid = o["action"], o["id"]
        try:
            if act == "ack":
                res = link.ack(oid)
            elif act == "build" and build:
                res = link.built(oid, build(o))
            elif act == "review" and review:
                verdict, findings, sha = review(o)
                res = link.qc(oid, verdict, findings, sha)
            else:
                res = {"status": "skipped", "message": "no handler for %s" % act}
        except Exception as e:                      # the order simply stays where it is; nothing is reported as done
            res = {"status": "error", "message": "%s: %s" % (type(e).__name__, e)}
        done.append({"order": oid, "action": act, "result": res})
    return done


def serve(link, build=None, review=None, interval=15, log=print):
    log("orchestrator %s is listening for orders every %ss (Ctrl+C to stop)" % (link.orchestrator, interval))
    try:
        while True:
            for d in run_once(link, build, review):
                log("%s %s -> %s" % (d["action"], d["order"], d["result"].get("status")))
            time.sleep(interval)
    except KeyboardInterrupt:
        log("stopped")
