"""orchestrator_client.py - what an engine's ORCHESTRATOR uses to talk to NEXXUS over the orchestrator bus.

An engine's governor creates one client with its engine name and its registered orchestrator id, then:
    link = OrchestratorClient("axis-video_creator", "video_creator.governor")
    link.ack(order_id)                          # "I received the order"
    link.built(order_id, "/path/to/artifact")   # "I built it" (NEXXUS hashes the file itself)
    link.qc(order_id, "pass", [], sha256)       # only from a QC-reviewer engine, never for its own build
Every message is signed with NEXXUS_GOVERNANCE_SECRET and sent to NEXXUS's /api/bus/message. Silos never use this: only the orchestrator.
Standard library only. `transport` can be replaced in tests.
"""
import json
import os
import urllib.error
import urllib.request

from orchestrator_bus import sign_envelope


class OrchestratorClient:
    def __init__(self, engine, orchestrator, url=None, secret=None, transport=None):
        self.engine = engine
        self.orchestrator = orchestrator
        self.url = (url or os.environ.get("NEXXUS_MESH_URL", "http://127.0.0.1:8000")).rstrip("/")
        self._secret = (secret or os.environ.get("NEXXUS_GOVERNANCE_SECRET", "")).encode() if not isinstance(secret, bytes) else secret
        if not self._secret:
            raise RuntimeError("no signing secret: set NEXXUS_GOVERNANCE_SECRET")
        self._transport = transport or self._http

    def _http(self, path, payload):
        req = urllib.request.Request(self.url + path, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except ValueError:
                return {"status": "error", "message": "HTTP %d" % e.code}
        except (urllib.error.URLError, OSError) as e:
            return {"status": "error", "message": "NEXXUS is not reachable: %s" % e}

    def _send(self, kind, body):
        return self._transport("/api/bus/message", sign_envelope(self._secret, self.orchestrator, "nexxus", kind, body))

    def poll(self):
        """-> {status, orders:[{id, action, spec, ...}]}: what this orchestrator has to do right now."""
        return self._transport("/api/bus/poll", sign_envelope(self._secret, self.orchestrator, "nexxus", "poll", {}))

    def audit(self, kind, detail=""):
        """Report an event that happened inside this engine. It goes into NEXXUS's ledger and on to the auditor engine."""
        return self._send("audit", {"kind": kind, "detail": detail})

    def audit_ack(self, upto):
        """For an auditor engine: confirm that events up to number `upto` are written into its own record."""
        return self._send("audit_ack", {"upto": upto})

    def ack(self, order_id):
        return self._send("ack", {"order_id": order_id})

    def built(self, order_id, artifact):
        return self._send("built", {"order_id": order_id, "artifact": os.path.abspath(artifact)})

    def qc(self, order_id, verdict, findings=None, artifact_sha256=None):
        return self._send("qc", {"order_id": order_id, "verdict": verdict, "findings": findings or [], "artifact_sha256": artifact_sha256})
