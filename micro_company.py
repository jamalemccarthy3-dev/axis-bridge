"""micro_company.py - a small autonomous operation: bots that run named tasks on a schedule and hand each result to the next bot.

What is real here: the scheduler thread, the task-routing chain (`then`), every handler's effect, the run ledger and the kill switch.
What a bot can do is a FIXED list; each task is a real call into this system through `services` (the server passes them in; tests pass fakes):
    health_check   the server's own health report
    creation_job   start a Creation-mode job (a page) from a prompt
    video_make     render a real mp4 (text-card explainer) from the brief and file it in the Creations hub
    publish_stage  stage a finished video in the publishing queue (private; approval stays with the owner)
    channel_check  verify the configured YouTube channel (read only)
    webhook        POST a JSON body to an https host the OWNER put on the allow-list (no redirects, 20 KB cap); with an empty list there is no outbound call at all
    report         write a markdown report of the recent runs
NOT possible, by design: placing phone calls, sending SMS or telemarketing. A bot whose task names a call/dial/sms/telemarket action is refused at validation with that explanation;
outbound contact with people is something the owner does, or hands to a service they are licensed and consented for through an allow-listed webhook.
Safety: a per-bot hourly run cap, a global hourly cap, a chain depth limit, a run timeout per task, a hash-chained run ledger, and stop() that takes effect before the next task starts.
"""
import hashlib
import json
import re
import threading
import time
import urllib.parse
from pathlib import Path

TASKS = ("health_check", "creation_job", "video_make", "publish_stage", "channel_check", "webhook", "report")
_BANNED = re.compile(r"call|dial|phone|sms|text_message|telemarket|robo|voicemail|cold_?out", re.I)
MAX_BOTS = 20
MAX_DEPTH = 8
HOURLY_BOT_CAP = 60
HOURLY_TOTAL_CAP = 600
MIN_EVERY = 5


class CompanyError(Exception):
    pass


def validate(config):
    """-> the clean spec: {"company", "bots": [...], "webhook_allow": [...]}. Raises CompanyError with a reason the owner can act on."""
    name = str(config.get("company") or "").strip()
    if not name:
        raise CompanyError("the company needs a name")
    bots = config.get("bots")
    if isinstance(bots, str):
        try:
            bots = json.loads(bots)
        except ValueError:
            raise CompanyError("bots must be valid JSON: a list of {name, task, params, every_s, then}")
    if not isinstance(bots, list) or not bots or len(bots) > MAX_BOTS:
        raise CompanyError("bots must be a list of 1 to %d bots" % MAX_BOTS)
    allow = [str(h).strip().lower() for h in (config.get("webhook_allow") or []) if str(h).strip()]
    for h in allow:
        if not re.match(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", h) or "." not in h:
            raise CompanyError("webhook host %r is not a plain host name" % h)
    clean, names = [], set()
    for i, b in enumerate(bots):
        if not isinstance(b, dict):
            raise CompanyError("bot %d must be an object" % (i + 1))
        bn, task = str(b.get("name") or "").strip(), str(b.get("task") or "").strip()
        if not re.match(r"^[A-Za-z][A-Za-z0-9 _-]{0,39}$", bn):
            raise CompanyError("bot %d needs a name (letters, digits, space, - _; up to 40)" % (i + 1))
        if bn in names:
            raise CompanyError("two bots are named %r" % bn)
        names.add(bn)
        if _BANNED.search(task):
            raise CompanyError("bot %r: %r is a phone/SMS/telemarketing action. This system does not place calls or send texts to people; "
                               "give that step to a service you are licensed and have consent for, and let a bot hand it work through an allow-listed webhook" % (bn, task))
        if task not in TASKS:
            raise CompanyError("bot %r: unknown task %r (tasks: %s)" % (bn, task, ", ".join(TASKS)))
        params = b.get("params") or {}
        if not isinstance(params, dict):
            raise CompanyError("bot %r: params must be an object" % bn)
        ev = b.get("every_s")
        if ev is not None and (isinstance(ev, bool) or not isinstance(ev, (int, float)) or ev < MIN_EVERY or ev > 604800):
            raise CompanyError("bot %r: every_s must be %d to 604800 seconds (or left out to run only when another bot hands it work)" % (bn, MIN_EVERY))
        if task == "webhook" and not allow:
            raise CompanyError("bot %r calls a webhook but no webhook host is allowed; add the https host to webhook_allow" % bn)
        clean.append({"name": bn, "task": task, "params": params, "every_s": ev, "then": (str(b["then"]).strip() if b.get("then") else None)})
    for b in clean:
        if b["then"] and b["then"] not in names:
            raise CompanyError("bot %r hands work to %r, which is not a bot in this company" % (b["name"], b["then"]))
        seen, cur = set(), b["name"]
        while cur:                                                       # a loop in the hand-off chain would run forever
            if cur in seen:
                raise CompanyError("the hand-off chain starting at %r loops back on itself" % b["name"])
            seen.add(cur)
            cur = next(x["then"] for x in clean if x["name"] == cur)
    return {"company": name, "purpose": str(config.get("purpose") or "")[:600], "bots": clean, "webhook_allow": allow}


def _https_post(url, body, timeout=15):
    import http.client
    u = urllib.parse.urlsplit(url)
    c = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=timeout)
    try:
        c.request("POST", (u.path or "/") + ("?" + u.query if u.query else ""), body=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
        r = c.getresponse()
        return r.status
    finally:
        c.close()


class MicroCompany:
    def __init__(self, workdir, config, services, now=time.time, post=_https_post):
        self.spec = validate(config)
        self.dir = Path(workdir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.services, self.now, self.post = services, now, post
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._ledger = self.dir / "runs.jsonl"
        self._last = "0" * 64
        self.runs = []
        self._due = {b["name"]: 0.0 for b in self.spec["bots"] if b["every_s"]}
        self._hist = {}                                                   # bot -> run timestamps in the last hour
        self.started_at = None

    # ---- ledger ----
    def _log(self, rec):
        rec = dict(rec, t=round(self.now(), 3), prev=self._last)
        rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        with open(self._ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
        self._last = rec["hash"]
        self.runs.append(rec)
        del self.runs[:-300]

    def _allowed(self, bot):
        cut = self.now() - 3600
        h = self._hist.setdefault(bot, [])
        h[:] = [t for t in h if t > cut]
        total = sum(len([t for t in v if t > cut]) for v in self._hist.values())
        if len(h) >= HOURLY_BOT_CAP or total >= HOURLY_TOTAL_CAP:
            return False
        h.append(self.now())
        return True

    # ---- handlers ----
    def _do(self, bot, upstream):
        p, svc, t = bot["params"], self.services, bot["task"]
        if t == "health_check":
            return svc["health"]()
        if t == "creation_job":
            prompt = str(p.get("prompt") or (upstream or {}).get("prompt") or "").strip()
            if not prompt:
                raise CompanyError("creation_job needs params.prompt")
            return dict(svc["creation"](prompt), prompt=prompt)
        if t == "video_make":
            title = str(p.get("title") or (upstream or {}).get("title") or "").strip()
            lines = p.get("lines") or (upstream or {}).get("lines") or []
            if not title or not lines:
                raise CompanyError("video_make needs a title and lines (params, or from the bot before it)")
            return svc["video"](title, lines, p.get("seconds_per_card", 3))
        if t == "publish_stage":
            cid = str(p.get("creation_id") or (upstream or {}).get("creation_id") or "").strip()
            if not cid:
                raise CompanyError("publish_stage needs a creation_id (params or from the bot before it)")
            return {"staged": svc["stage"](cid, p.get("title") or "Untitled", p.get("description", ""), p.get("tags") or [], p.get("topic", ""))}
        if t == "channel_check":
            return {"channel": svc["channel"]()}
        if t == "webhook":
            url = str(p.get("url") or "")
            u = urllib.parse.urlsplit(url)
            if u.scheme != "https" or (u.hostname or "").lower() not in self.spec["webhook_allow"]:
                raise CompanyError("the webhook host is not on the owner's allow-list (https only)")
            body = {"company": self.spec["company"], "bot": bot["name"], "data": upstream or {}}
            if len(json.dumps(body, default=str)) > 20000:
                raise CompanyError("the webhook body is over 20 KB")
            return {"status": self.post(url, body)}
        if t == "report":
            return {"report": self._report()}
        raise CompanyError("unknown task")

    def _report(self):
        ok = sum(1 for r in self.runs if r.get("ok"))
        lines = ["# %s - run report" % self.spec["company"], "", "%d runs, %d ok, %d failed" % (len(self.runs), ok, len(self.runs) - ok), ""]
        lines += ["- %s  %s  %s%s" % (time.strftime("%H:%M:%S", time.localtime(r["t"])), r["bot"], "ok" if r.get("ok") else "FAILED", "" if r.get("ok") else ": " + str(r.get("error"))) for r in self.runs[-50:]]
        (self.dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return "report.md"

    # ---- running ----
    def run_bot(self, name, upstream=None, depth=0):
        """Run one bot, then follow its hand-off chain. -> list of run records. Safe to call from any thread."""
        out = []
        while name and depth <= MAX_DEPTH and not self._stop.is_set():
            bot = next((b for b in self.spec["bots"] if b["name"] == name), None)
            if bot is None:
                break
            with self._lock:
                if not self._allowed(name):
                    self._log({"bot": name, "task": bot["task"], "ok": False, "error": "hourly run cap reached", "depth": depth})
                    out.append(self.runs[-1])
                    break
            t0 = time.perf_counter()
            try:
                res = self._do(bot, upstream)
                rec = {"bot": name, "task": bot["task"], "ok": True, "result": _brief(res), "depth": depth}
            except Exception as e:                                         # one bot failing must not stop the company
                res, rec = None, {"bot": name, "task": bot["task"], "ok": False, "error": ("%s: %s" % (type(e).__name__, e))[:300], "depth": depth}
            rec["ms"] = round((time.perf_counter() - t0) * 1000, 2)
            with self._lock:
                self._log(rec)
                out.append(self.runs[-1])
            if not rec["ok"]:
                break
            upstream, name, depth = res if isinstance(res, dict) else {"value": res}, bot["then"], depth + 1
        return out

    def _loop(self):
        while not self._stop.wait(0.2):
            t = self.now()
            for name, due in list(self._due.items()):
                if t >= due and not self._stop.is_set():
                    bot = next(b for b in self.spec["bots"] if b["name"] == name)
                    self._due[name] = t + bot["every_s"]
                    self.run_bot(name)

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()
            self.started_at = self.now()
            self._thread = threading.Thread(target=self._loop, name="micro-company-%s" % self.spec["company"][:20], daemon=True)
            self._thread.start()
            return True

    def stop(self, wait=5):
        self._stop.set()
        th = self._thread
        if th and th.is_alive() and th is not threading.current_thread():
            th.join(wait)
        return not (th and th.is_alive())

    def running(self):
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def status(self):
        with self._lock:
            return {"company": self.spec["company"], "running": self.running(), "bots": [dict(b, next_in_s=(round(max(0, self._due[b["name"]] - self.now()), 1) if b["name"] in self._due and self.running() else None)) for b in self.spec["bots"]],
                    "runs": len(self.runs), "failed": sum(1 for r in self.runs if not r.get("ok")), "recent": self.runs[-20:]}

    def verify_ledger(self):
        prev, n = "0" * 64, 0
        try:
            lines = self._ledger.read_text(encoding="utf-8").splitlines() if self._ledger.is_file() else []
        except OSError:
            return False, 0
        for n, line in enumerate(lines, 1):
            try:
                rec = json.loads(line)
                h = rec.pop("hash")
            except (ValueError, KeyError):
                return False, n
            if rec.get("prev") != prev or hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode("utf-8")).hexdigest() != h:
                return False, n
            prev = h
        return True, n


def _brief(res):
    s = json.dumps(res, default=str)
    return res if len(s) <= 1500 else {"truncated": s[:1500]}
