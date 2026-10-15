"""witness.py - axis-integrity checks what an engine CLAIMS against what is true, and against the engine's own sequence of reports.

The Auditor (lib/auditor.py) proves a record was not changed afterwards. The witness is the other half: it asks whether the record is believable.
It does not use any of core's code: the rules below are written again here on purpose, so a mistake or a lie inside core cannot also fool its checker.

Checks on core's reports (see axis-core/orchestrator.py for the events):
  * PURGE_DONE with no PURGE_REQUESTED for that folder               -> CRITICAL: something was deleted without a request
  * PURGE_DONE, but files that are not on the allow-list are still there -> CRITICAL: the claim is false
  * PURGE_DONE for a folder that does not exist                       -> WARNING
  * PURGE_REPORT_ONLY that claims N files, but a file it listed is gone  (the 'report only' purge removed something) -> CRITICAL
  * PURGE_REQUESTED that never finishes (needs `now`)                 -> WARNING: unfinished
  * SECURITY_ARMED without SECURITY_ARMING before it                  -> WARNING;  SECURITY_ARM_FAILED -> WARNING
Every finding is returned and, when an Auditor is given, written into its chain as FINDING:<SEVERITY>.
"""
import os
import time

ALLOWED = {"axis_switchboard.exe", "sender.exe"}      # what axis-core's folder may contain (the purge rule, restated independently)
SEVERITIES = ("CRITICAL", "WARNING", "INFO")


def ghosts_in(folder):
    """Regular files in `folder` that are not on the allow-list (sub-folders are ignored, as the purge rule says). None when the folder is missing."""
    if not os.path.isdir(folder):
        return None
    return sorted(f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)) and f not in ALLOWED)


def _folder(detail):
    """PURGE_* details are "<folder>" or "<folder>: <n> file(s)". Windows folders contain ':' (C:\\...), so split on the LAST ': <digits> file'."""
    marker = ": "
    if marker in detail and detail.rsplit(marker, 1)[1].split(" ")[0].lstrip("-").isdigit():
        return detail.rsplit(marker, 1)[0]
    return detail


class Witness:
    def __init__(self, auditor=None, now=time.time, unfinished_after=300.0):
        self.auditor = auditor
        self.now = now
        self.unfinished_after = unfinished_after
        self.open_requests = {}         # folder -> (event number, time seen)
        self.arming = False
        self.report_only = {}           # folder -> ghost files listed at report time (for the later 'nothing was removed' check)

    def _finding(self, severity, message, ev, out):
        f = {"severity": severity, "message": message, "event": ev["n"], "engine": ev["engine"]}
        out.append(f)
        if self.auditor is not None:
            self.auditor.log_event("FINDING:" + severity, "event #%d from %s: %s" % (ev["n"], ev["engine"], message))

    def check(self, events):
        """events: [{n, engine, kind, detail}] oldest first. -> the list of findings (empty when everything agrees)."""
        out = []
        for ev in events:
            kind, detail = ev["kind"], str(ev.get("detail", ""))
            if kind == "PURGE_REQUESTED":
                self.open_requests[_folder(detail)] = (ev["n"], self.now())
            elif kind in ("PURGE_DONE", "PURGE_REFUSED"):
                folder = _folder(detail)
                if folder not in self.open_requests:
                    self._finding("CRITICAL" if kind == "PURGE_DONE" else "WARNING", "%s for %s with no PURGE_REQUESTED before it" % (kind, folder), ev, out)
                else:
                    del self.open_requests[folder]
                if kind == "PURGE_DONE":
                    left = ghosts_in(folder)
                    if left is None:
                        self._finding("WARNING", "the purged folder %s does not exist" % folder, ev, out)
                    elif left:
                        self._finding("CRITICAL", "core reported the purge of %s as done, but %d file(s) that are not on the allow-list are still there: %s" % (folder, len(left), ", ".join(left[:5])), ev, out)
            elif kind == "PURGE_REPORT_ONLY":
                folder = _folder(detail)
                self.report_only[folder] = ghosts_in(folder) or []
            elif kind == "SECURITY_ARMING":
                self.arming = True
            elif kind == "SECURITY_ARMED":
                if not self.arming:
                    self._finding("WARNING", "SECURITY_ARMED without a SECURITY_ARMING before it", ev, out)
                self.arming = False
            elif kind == "SECURITY_ARM_FAILED":
                self._finding("WARNING", "core could not arm its security lock: %s" % detail, ev, out)
                self.arming = False
        # a 'report only' purge must not have removed anything: every file it listed must still be there
        for folder, listed in list(self.report_only.items()):
            gone = [f for f in listed if not os.path.isfile(os.path.join(folder, f))]
            if gone and events:
                self._finding("CRITICAL", "a report-only purge of %s listed files that have since disappeared: %s (they may have been removed by something that was not reported)" % (folder, ", ".join(gone[:5])), events[-1], out)
                del self.report_only[folder]
        # requests that never finished
        for folder, (n, seen) in list(self.open_requests.items()):
            if self.now() - seen > self.unfinished_after:
                self._finding("WARNING", "the purge requested for %s (event #%d) never finished" % (folder, n), {"n": n, "engine": "axis-core"}, out)
                del self.open_requests[folder]
        return out
