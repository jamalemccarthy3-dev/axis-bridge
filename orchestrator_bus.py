"""orchestrator_bus.py - how NEXXUS works with the engines' ORCHESTRATORS, and only with them.

Why it exists: NEXXUS must be able to give an engine a build order and get a trustworthy answer back, without ever talking to a silo inside
the engine and without any way to skip quality control.

The rules, enforced here (not just promised):
  1. Only orchestrators are addressable. An order or message for a silo, or for an engine that has no registered orchestrator, is refused.
  2. Every message is a signed envelope (HMAC-SHA256, fresh timestamp, single use). A forged, stale or replayed envelope is refused, and
     a sender can only speak as the orchestrator that was registered for its engine.
  3. A build moves through fixed states and cannot skip any:
         ORDERED -> ACKED -> BUILT -> QC_PASSED -> ACCEPTED        (QC_FAILED sends it back to ACKED for rework)
  4. Quality control is independent. The QC verdict must come from a different engine than the builder (a builder can never grade its own
     work), and a pass is only accepted for the exact artifact that was built (its SHA-256 is checked again at QC time).
  5. Only NEXXUS accepts. At accept time the artifact is hashed AGAIN (if it changed after QC the build is refused) and NEXXUS's own
     checks run, so an engine reporting "done" is never enough.
  6. Everything is written to an append-only, hash-chained ledger. verify_ledger() detects any edited, removed or reordered entry.

Free, local, standard library only. It does not start engines or run code: it is the rulebook and the record.
"""
import hashlib
import hmac
import json
import os
import threading
import time
import uuid

MAX_AGE_SECONDS = 60
STATES = ("ORDERED", "ACKED", "BUILT", "QC_PASSED", "QC_FAILED", "ACCEPTED", "REJECTED")


class BusError(Exception):
    """A rule of the bus was broken. The message says which rule, never any secret."""


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def sign_envelope(secret, sender, to, kind, body, ts=None, clock=time.time):
    """Make a signed message. Used by the bus (for NEXXUS) and by orchestrator_client.py (for an engine's orchestrator)."""
    env = {"id": uuid.uuid4().hex, "ts": clock() if ts is None else ts, "sender": sender, "to": to, "kind": kind, "body": body}
    env["sig"] = hmac.new(secret, _canon(env), hashlib.sha256).hexdigest()
    return env


class OrchestratorBus:
    def __init__(self, ledger_path, secret=None, clock=time.time):
        self.ledger_path = ledger_path
        self._secret = (secret if secret is not None else os.environ.get("NEXXUS_GOVERNANCE_SECRET", "")).encode() if isinstance(secret, (str, type(None))) else secret
        if not self._secret:
            raise BusError("no signing secret: set NEXXUS_GOVERNANCE_SECRET or pass secret=")
        self._clock = clock
        self._lock = threading.RLock()
        self.orchestrators = {}      # engine -> orchestrator id (the ONLY addressable thing in an engine)
        self.qc_reviewers = set()    # engines allowed to issue QC verdicts
        self.auditors = set()        # engines that receive the audit feed (axis-integrity)
        self.audit_events = []       # every audit event any orchestrator reported, oldest first: {n, engine, kind, detail, ts}
        self._audit_cursor = {}      # auditor engine -> the number of the last event it confirmed
        self.nexxus_checks = []      # callables(order, artifact_path) -> list of finding dicts, run again at accept time
        self.orders = {}
        self._seen = {}              # envelope id -> timestamp (replay cache)
        self._last_hash = "0" * 64
        self._n = 0
        self._replay_ledger()

    # ---------------------------------------------------------------- ledger
    def _append(self, event, data):
        entry = {"n": self._n + 1, "ts": self._clock(), "event": event, "data": data, "prev": self._last_hash}
        entry["hash"] = hashlib.sha256(_canon(entry)).hexdigest()
        os.makedirs(os.path.dirname(os.path.abspath(self.ledger_path)), exist_ok=True)
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
        self._n, self._last_hash = entry["n"], entry["hash"]

    def _read_ledger(self):
        if not os.path.isfile(self.ledger_path):
            return []
        with open(self.ledger_path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def verify_ledger(self):
        """-> (True, count) or (False, number of the first bad entry). Detects edited, removed, inserted or reordered entries."""
        prev, n = "0" * 64, 0
        for e in self._read_ledger():
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev") != prev or e.get("n") != n + 1 or hashlib.sha256(_canon(body)).hexdigest() != e.get("hash"):
                return False, e.get("n", n + 1)
            prev, n = e["hash"], n + 1
        return True, n

    def _replay_ledger(self):
        ok, info = self.verify_ledger()
        if not ok:
            raise BusError("the ledger has been tampered with (first bad entry: %s)" % info)
        for e in self._read_ledger():
            self._n, self._last_hash = e["n"], e["hash"]
            d, ev = e["data"], e["event"]
            if ev == "register":
                self.orchestrators[d["engine"]] = d["orchestrator"]
                if d.get("qc_reviewer"):
                    self.qc_reviewers.add(d["engine"])
                if d.get("auditor"):
                    self.auditors.add(d["engine"])
            elif ev == "audit":
                self.audit_events.append(dict(d, ts=e["ts"]))
            elif ev == "audit_ack":
                self._audit_cursor[d["engine"]] = max(self._audit_cursor.get(d["engine"], 0), d["upto"])
            elif ev == "order":
                self.orders[d["id"]] = dict(d, state="ORDERED", history=[("ORDERED", e["ts"])])
            elif ev == "state" and d["id"] in self.orders:
                o = self.orders[d["id"]]
                o["state"] = d["state"]
                o["history"].append((d["state"], e["ts"]))
                for k in ("artifact", "artifact_sha256", "builder", "qc", "note"):
                    if k in d:
                        o[k] = d[k]

    def _set_state(self, order, state, **extra):
        order["state"] = state
        order["history"].append((state, self._clock()))
        order.update(extra)
        self._append("state", dict({"id": order["id"], "state": state}, **extra))

    # ---------------------------------------------------------------- registry
    def register_orchestrator(self, engine, orchestrator, qc_reviewer=False, auditor=False):
        """Make `orchestrator` the one door into `engine`. Only NEXXUS calls this."""
        with self._lock:
            self.orchestrators[engine] = orchestrator
            if qc_reviewer:
                self.qc_reviewers.add(engine)
            if auditor:
                self.auditors.add(engine)
            self._append("register", {"engine": engine, "orchestrator": orchestrator, "qc_reviewer": bool(qc_reviewer), "auditor": bool(auditor)})

    # ---------------------------------------------------------------- envelopes
    def make_envelope(self, sender, to, kind, body):
        """A signed message. (An engine's orchestrator makes these with the shared secret; NEXXUS makes its own.)"""
        return sign_envelope(self._secret, sender, to, kind, body, clock=self._clock)

    def _verify(self, env):
        sig = env.get("sig", "")
        body = {k: v for k, v in env.items() if k != "sig"}
        if not hmac.compare_digest(sig, hmac.new(self._secret, _canon(body), hashlib.sha256).hexdigest()):
            raise BusError("signature does not match: the message is forged or was changed")
        if abs(self._clock() - float(env.get("ts", 0))) > MAX_AGE_SECONDS:
            raise BusError("the message is stale (older than %d s)" % MAX_AGE_SECONDS)
        now = self._clock()
        self._seen = {k: t for k, t in self._seen.items() if now - t <= MAX_AGE_SECONDS}
        if env["id"] in self._seen:
            raise BusError("replayed message refused (each message can be used once)")
        self._seen[env["id"]] = now

    def _speaker(self, env):
        """The engine a sender speaks for: only a registered orchestrator counts."""
        for engine, orch in self.orchestrators.items():
            if env["sender"] == orch:
                return engine
        raise BusError("sender %r is not a registered orchestrator (silos cannot talk to NEXXUS)" % env.get("sender"))

    # ---------------------------------------------------------------- NEXXUS -> orchestrator
    def send_order(self, engine, to, spec):
        """NEXXUS gives `engine`'s orchestrator a build order. `to` must be that orchestrator: naming a silo is refused."""
        with self._lock:
            if engine not in self.orchestrators:
                raise BusError("engine %r has no registered orchestrator" % engine)
            if to != self.orchestrators[engine]:
                raise BusError("%r is not the orchestrator of %s: orders go to orchestrators only, never to a silo" % (to, engine))
            order = {"id": "ord_" + uuid.uuid4().hex[:10], "engine": engine, "to": to, "spec": spec, "state": "ORDERED", "history": [("ORDERED", self._clock())]}
            self.orders[order["id"]] = order
            self._append("order", {k: order[k] for k in ("id", "engine", "to", "spec")})
            return dict(order)

    # ---------------------------------------------------------------- orchestrator -> NEXXUS (signed)
    def receive(self, env):
        """Verify a signed envelope and apply it. kinds: ack | built | qc"""
        with self._lock:
            self._verify(env)
            engine = self._speaker(env)
            if env.get("to") != "nexxus":
                raise BusError("messages from an orchestrator go to NEXXUS only")
            kind, body = env["kind"], env.get("body") or {}
            if kind == "audit":
                return self._audit(engine, body)
            if kind == "audit_ack":
                return self._audit_ack(engine, body)
            order = self.orders.get(body.get("order_id"))
            if order is None:
                raise BusError("unknown order")
            if kind == "ack":
                return self._ack(order, engine)
            if kind == "built":
                return self._built(order, engine, body.get("artifact"))
            if kind == "qc":
                return self._qc(order, engine, body.get("verdict"), body.get("findings") or [], body.get("artifact_sha256"))
            raise BusError("unknown message kind %r" % kind)

    def _audit(self, engine, body):
        """An orchestrator reports something that happened inside its engine (a lock armed, a purge asked for ...). It is written to the ledger first;
        the auditor engines then receive it from the feed. -> {"audit_n": its number}"""
        kind, detail = body.get("kind"), body.get("detail", "")
        if not isinstance(kind, str) or not kind.strip() or len(kind) > 64:
            raise BusError("an audit event needs a short kind")
        detail = detail if isinstance(detail, str) else json.dumps(detail, default=str, sort_keys=True)
        if len(detail) > 2000:
            raise BusError("the audit detail is longer than 2000 characters")
        n = len(self.audit_events) + 1
        data = {"n": n, "engine": engine, "kind": kind.strip(), "detail": detail}
        self._append("audit", data)
        self.audit_events.append(dict(data, ts=self._clock()))
        return {"audit_n": n}

    def _audit_ack(self, engine, body):
        """An auditor confirms it has written events up to number `upto` into its own record. The feed then moves on."""
        if engine not in self.auditors:
            raise BusError("%s is not an auditor" % engine)
        upto = body.get("upto")
        if not isinstance(upto, int) or upto < 0 or upto > len(self.audit_events):
            raise BusError("upto must be a number between 0 and %d" % len(self.audit_events))
        self._append("audit_ack", {"engine": engine, "upto": upto})
        self._audit_cursor[engine] = max(self._audit_cursor.get(engine, 0), upto)
        return {"audit_cursor": self._audit_cursor[engine]}

    def _need(self, order, *states):
        if order["state"] not in states:
            raise BusError("order %s is %s; this step needs %s (no state can be skipped)" % (order["id"], order["state"], " or ".join(states)))

    def _ack(self, order, engine):
        if engine != order["engine"]:
            raise BusError("only the ordered engine's orchestrator can acknowledge this order")
        self._need(order, "ORDERED")
        self._set_state(order, "ACKED")
        return dict(order)

    def _built(self, order, engine, artifact):
        if engine != order["engine"]:
            raise BusError("only the ordered engine's orchestrator can report this build")
        self._need(order, "ACKED")
        if not artifact or not os.path.isfile(artifact):
            raise BusError("a build must name an artifact file that exists; NEXXUS hashes it itself")
        self._set_state(order, "BUILT", artifact=os.path.abspath(artifact), artifact_sha256=sha256_file(artifact), builder=engine)
        return dict(order)

    def _qc(self, order, reviewer, verdict, findings, claimed_sha):
        self._need(order, "BUILT")
        if reviewer not in self.qc_reviewers:
            raise BusError("%s is not a registered quality-control reviewer" % reviewer)
        if reviewer == order["builder"]:
            raise BusError("a builder can never grade its own work (QC must come from another engine)")
        if verdict not in ("pass", "fail"):
            raise BusError("the verdict must be pass or fail")
        now_sha = sha256_file(order["artifact"]) if os.path.isfile(order["artifact"]) else None
        if now_sha != order["artifact_sha256"]:
            raise BusError("the artifact changed (or vanished) since it was built: QC must review the built version")
        if verdict == "pass":
            if claimed_sha != order["artifact_sha256"]:
                raise BusError("a pass must name the SHA-256 of the exact artifact that was built")
            if any(f.get("severity") == "critical" for f in findings):
                raise BusError("a pass cannot carry a critical finding")
        qc = {"reviewer": reviewer, "verdict": verdict, "findings": findings, "artifact_sha256": claimed_sha}
        self._set_state(order, "QC_PASSED" if verdict == "pass" else "QC_FAILED", qc=qc)
        if verdict == "fail":                       # rework: the orchestrator may report a new build
            self._set_state(order, "ACKED", note="sent back for rework after QC failed")
        return dict(order)

    def poll(self, env):
        """An orchestrator asks what it has to do (signed like every other message). -> a list of {id, action, spec, ...}
        action: ack (new order) | build (acknowledged, or sent back after a failed QC) | review (QC reviewers only, never for their own build)."""
        with self._lock:
            self._verify(env)
            engine = self._speaker(env)
            if env.get("kind") != "poll" or env.get("to") != "nexxus":
                raise BusError("a poll must be a signed 'poll' message to NEXXUS")
            out = []
            if engine in self.auditors:
                pending = self.audit_events[self._audit_cursor.get(engine, 0):][:50]
                if pending:
                    out.append({"id": "audit_feed", "action": "audit", "events": pending, "upto": pending[-1]["n"]})
            for o in self.orders.values():
                if o["engine"] == engine and o["state"] == "ORDERED":
                    out.append({"id": o["id"], "action": "ack", "spec": o["spec"]})
                elif o["engine"] == engine and o["state"] == "ACKED":
                    out.append({"id": o["id"], "action": "build", "spec": o["spec"], "note": o.get("note")})
                elif engine in self.qc_reviewers and o["state"] == "BUILT" and o.get("builder") != engine:
                    out.append({"id": o["id"], "action": "review", "spec": o["spec"], "artifact": o["artifact"], "artifact_sha256": o["artifact_sha256"], "builder": o["builder"]})
            return out

    # ---------------------------------------------------------------- NEXXUS decides
    def accept(self, order_id):
        """Only NEXXUS can accept, and only a QC-passed order whose artifact is still exactly what was reviewed."""
        with self._lock:
            order = self.orders.get(order_id)
            if order is None:
                raise BusError("unknown order")
            self._need(order, "QC_PASSED")
            if not os.path.isfile(order["artifact"]) or sha256_file(order["artifact"]) != order["qc"]["artifact_sha256"]:
                raise BusError("the artifact no longer matches what QC reviewed: refused")
            findings = []
            for check in self.nexxus_checks:
                findings += list(check(order, order["artifact"]) or [])
            crit = [f for f in findings if f.get("severity") == "critical"]
            if crit:
                self._set_state(order, "REJECTED", note="NEXXUS's own check found: " + "; ".join(str(f.get("message")) for f in crit))
                raise BusError("NEXXUS's own checks refused it: " + "; ".join(str(f.get("message")) for f in crit))
            self._set_state(order, "ACCEPTED")
            return dict(order)

    def status(self, order_id):
        o = self.orders.get(order_id)
        return None if o is None else {k: o.get(k) for k in ("id", "engine", "state", "builder", "artifact_sha256", "qc", "note")}
