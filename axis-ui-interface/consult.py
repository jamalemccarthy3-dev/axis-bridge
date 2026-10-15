# Final Copy: The Silent Consultant Network (the gate's front door)
#
# NEXXUS stays the one intelligence the outside world sees. When a job is stuck, it can quietly ask a "consultant":
# a free model server on ANOTHER computer on your own network. Every question goes through this gate and nothing else:
#
#   Registry  - a consultant must be registered ...
#   Protocol  - ... through the handshake before it can be called
#   Shield    - every outgoing message is screened and scrubbed (secrets, emails, phone numbers, user paths) and is
#               limited to the job's own text and files; nothing else can leave
#   Audit     - every consult is written to the owner's PRIVATE log (consult_private.jsonl); it is never shown in the UI
#
# What comes back is ADVICE, nothing more: text. It is never executed. If it contains code, the caller treats it as a
# candidate that must pass the same tests / checks as anything else. If a consultant is off, unreachable, over its daily
# budget or its circuit breaker is open, ask() just returns None and NEXXUS carries on alone - nobody is told.
import os
import re
import time

from registry import Registry
from protocol import Protocol
from shield import Shield
from audit import Audit
from consult_config import ConsultConfig, STATE_FILE, LOG_FILE, TASKS
from consult_tool import ConsultTool, scrub, secret_values_in, clean_reply, url_ok

CONSULT_SYSTEM = (
    "You are a senior engineer giving a second opinion to a colleague whose own tools are stuck. "
    "Work only from the material below. Be concise: a short diagnosis first, then the corrected COMPLETE file(s) if you can. "
    "Do not ask questions and do not add commentary about yourself."
)


class _Port:
    """The minimal 'system port' the Registry / Protocol / Audit pieces expect."""
    def acknowledge_registry(self, project_id):
        pass


class _LedgerAudit(Audit):
    """The usual in-memory Audit, plus every event goes to the owner's private log."""
    def __init__(self, system_port, tool):
        super().__init__(system_port)
        self._tool = tool

    def record_event(self, event_type, project_id, details):
        ok = super().record_event(event_type, project_id, details)
        del self.logs[:-500]
        self._tool.log({"event": event_type, "consultant": project_id, "details": str(details)[:300]})
        return ok


class ConsultShield(Shield):
    """The barrier: decides what may leave and scrubs it."""
    def screen(self, policy, task, files, error_output):
        """-> (prompt, redactions) or (None, reason)."""
        cap, total = policy["max_input_chars"], 0
        t, k = scrub(task); total += k; t = t[:4000]
        e, k = scrub(error_output or ""); total += k; e = e[:4000]
        budget = max(0, cap - len(t) - len(e) - 400)
        parts = []
        for name, content in sorted((files or {}).items(), key=lambda kv: len(str(kv[1]))):    # small files first: they survive truncation
            safe = re.sub(r"[^A-Za-z0-9._/-]", "_", os.path.basename(str(name).replace("\\", "/")))[:80] or "file"
            body, k = scrub(content); total += k
            if budget <= 200:
                break
            body = body[:budget]; budget -= len(body)
            parts.append("### FILE: %s\n```\n%s\n```" % (safe, body))
        if total > 40:
            return None, "too many sensitive-looking items (%d): not sent" % total
        prompt = "TASK:\n%s\n" % t
        if e:
            prompt += "\nERROR OUTPUT:\n%s\n" % e
        if parts:
            prompt += "\nFILES:\n" + "\n\n".join(parts)
        if secret_values_in(prompt):
            return None, "a secret value was still present: not sent"
        return prompt, total


def _axis_gate():
    """The axis gate guardian (project-X/axis_gate), or None when it cannot be loaded."""
    try:
        import axis_gate
        return axis_gate
    except ImportError:
        import sys
        px = os.path.join(os.path.dirname(os.path.abspath(__file__)), "project-X")
        if px not in sys.path:
            sys.path.insert(0, px)
        try:
            import axis_gate
            return axis_gate
        except ImportError:
            return None


class Consult:
    def __init__(self, system_port=None, config_path=None, state_file=None, log_file=None, axis_gate_required=True):
        # Every question must carry a single-use clearance from the axis gate (see consult_client.ask). Only a test harness may switch this off.
        self._gate_required = bool(axis_gate_required)
        self.system_port = system_port or _Port()
        self.state_file = state_file or STATE_FILE
        self.log_file = log_file or LOG_FILE
        self.config = ConsultConfig(config_path)
        self.tool = ConsultTool(self)
        self.audit = _LedgerAudit(self.system_port, self.tool)
        self.registry = Registry(self.system_port)
        self.protocol = Protocol(self.system_port, self.registry)
        self.shield = ConsultShield("consult-network", self.system_port)
        self._connect()

    def _connect(self):
        """Handshake every ENABLED consultant. Only a consultant that completes it can ever be called."""
        for p in self.config.problems:
            self.audit.record_event("CONFIG_NOTE", "config", p)
        if not self.config.master_enabled():
            return
        for c in self.config.get_consultants():
            if not c["enabled"]:
                continue
            target = c["host"] if c["kind"] == "ollama" else c["base_url"]
            if not url_ok(target):
                self.audit.record_event("HANDSHAKE_DENIED", c["id"], "address is not on your own network")
                continue
            ok = self.protocol.execute_handshake(c["id"], "consult:" + c["kind"])
            self.audit.record_event("HANDSHAKE_OK" if ok else "HANDSHAKE_DENIED", c["id"], c["kind"])

    def _ineligible(self, c, kind, policy):
        if not c["enabled"]:
            return "disabled"
        if kind not in c["for"]:
            return "not for this kind of task"
        if not self.registry.tool.verify_identity(c["id"]):
            return "not handshaken"
        if self.tool.breaker_open(c["id"]):
            return "circuit breaker open"
        return None

    def _cleared(self, clearance):
        """Spend the axis gate's single-use clearance. No clearance, a used one, an expired one, or no gate at all means nothing leaves."""
        if not self._gate_required:
            return True
        ag = _axis_gate()
        return bool(ag is not None and clearance and ag.redeem_ticket(clearance, "consult", source="consult").allow)

    def ask(self, kind, task, files=None, error_output=None, instructions="", clearance=None):
        """The one way in. -> {"ok": True, "text": advice} or None (silently) for any reason at all."""
        try:
            if kind not in TASKS or not self.config.master_enabled():
                return None
            if not self._cleared(clearance):
                self.audit.record_event("REFUSED", "gate", "no valid axis gate clearance")
                return None
            policy = self.config.get_policy()
            prompt, info = self.shield.screen(policy, task, files, error_output)
            if prompt is None:
                self.audit.record_event("REFUSED", "gate", info)
                return None
            if self.tool.calls_today() >= policy["max_calls_per_day"]:
                self.audit.record_event("BUDGET", "gate", "daily limit reached (%d)" % policy["max_calls_per_day"])
                return None
            system = CONSULT_SYSTEM + ("\n" + instructions if instructions else "")
            for c in self.config.get_consultants():
                if self._ineligible(c, kind, policy):
                    continue
                self.tool.count_call(c["id"])             # an attempt counts, so a failing consultant cannot be hammered
                t0 = time.time()
                try:
                    text, toks = self.tool.complete(c, system, prompt, policy["max_output_tokens"], policy["timeout_s"])
                except Exception as e:
                    self.tool.breaker_failed(c["id"], policy["breaker_failures"], policy["breaker_cooldown_s"])
                    self.tool.log({"event": "CONSULT", "consultant": c["id"], "task": kind, "status": "failed",
                                   "error": type(e).__name__, "ms": int((time.time() - t0) * 1000)})
                    continue
                clean = clean_reply(text, policy["max_output_tokens"] * 4)
                self.tool.count_tokens(c["id"], toks)
                self.tool.breaker_ok(c["id"])
                self.tool.log({"event": "CONSULT", "consultant": c["id"], "task": kind, "status": "ok", "in_chars": len(prompt),
                               "out_chars": len(clean), "redactions": info, "ms": int((time.time() - t0) * 1000),
                               "prompt_preview": prompt[:300], "reply_preview": clean[:300]})
                return {"ok": True, "text": clean}
            return None
        except Exception:
            return None                                   # the gate must never break a job

    def status(self):
        """For the owner (admin-token endpoint) only."""
        policy = self.config.get_policy()
        cons = []
        for c in self.config.get_consultants():
            u = self.tool.usage(c["id"])
            cons.append({"id": c["id"], "kind": c["kind"], "enabled": c["enabled"], "handshaken": self.registry.tool.verify_identity(c["id"]),
                         "calls_today": u["calls"], "tokens_today": u["tokens"], "breaker_open": u["breaker_open"]})
        return {"enabled": self.config.master_enabled(), "calls_today": self.tool.calls_today(), "daily_limit": policy["max_calls_per_day"],
                "consultants": cons, "problems": list(self.config.problems), "recent": self.tool.log_tail(20)}
