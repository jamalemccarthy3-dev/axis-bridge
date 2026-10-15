"""opportunity_desk.py - find real funding opportunities, check them against your entity vault, ask for exactly what is missing, and, once you sign off, compile an accurate application packet.

What this is built to do, and what it will not do:
  * DISCOVER from the official Grants.gov search API (public, no key) or from an opportunity you add by hand. Read-only requests, one at a time, rate limited; nothing is scraped from pages.
  * CHECK each one against your entity vault: eligibility (the applicant types the funder allows against your entity type), and which of its requirements your vault already answers.
  * ASK: the gap analysis turns every missing fact into a question; your answers go into the vault.
  * COMPILE, only after you sign off, a packet that says what your organisation really is: its facts come from the vault, its team is the people listed in it, its history is the past work listed in it.
    A claims check runs first and BLOCKS the packet if any text overstates the organisation: more staff than the vault lists, more years of experience than the organisation has existed, or a
    request the organisation is not eligible for. Polish comes from clean structure and complete, well-formatted sections, not from claims.
  * It never submits anything. The packet is prepared for YOU to submit through the funder's own portal, under your own name, and the submission notes say so.
  * It never stores an EIN, SSN, bank or card number: those are entered at the funder's portal. Nothing here creates accounts, registrations or entities.
Everything it does is written to a hash-chained ledger.
"""
import datetime
import hashlib
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

GRANTS_SEARCH = "https://api.grants.gov/v1/api/search2"
GRANTS_DETAIL = "https://api.grants.gov/v1/api/fetchOpportunity"
USER_AGENT = "NEXXUS-opportunity-desk/1.0 (owner tool; read-only)"
MIN_GAP_S = 2.0
ENTITY_TYPES = ("sole_proprietor", "llc", "s_corp", "c_corp", "partnership", "nonprofit_501c3", "other_nonprofit", "other")
STAFF_WORDS = r"(?:employees|staff|professionals|experts|consultants|engineers|developers|designers|analysts|specialists|associates|team members|people|colleagues|researchers|writers|advisors|advisers)"


class DeskError(Exception):
    pass


# ---- the entity vault: what is true about the organisation ----
def F(path, label, kind="text", required=False, help="", choices=None):
    d = {"path": path, "label": label, "kind": kind, "required": required, "help": help}
    if choices:
        d["choices"] = list(choices)
    return d


FIELDS = [
    F("org.legal_name", "Legal name of the organisation or the person it trades as", required=True),
    F("org.entity_type", "Entity type", "choice", True, "The funder's applicant types are matched against this.", ENTITY_TYPES),
    F("org.state", "State or country of formation", required=True), F("org.year_founded", "Year it began operating", "number", True),
    F("org.address", "Business address", "textarea", True), F("org.website", "Website"),
    F("org.mission", "What the organisation does, in your own words", "textarea", True), F("org.services", "Services or programmes offered", "list", True),
    F("org.naics", "NAICS codes", "list"), F("org.uei", "SAM.gov Unique Entity ID (if you have registered; you do this yourself)"), F("org.sam_registered", "Registered in SAM.gov", "toggle"),
    F("org.small_business", "Qualifies as a small business for the work you bid on", "toggle"), F("org.certifications", "Certifications and licences you really hold", "list"),
    F("contact.name", "Contact person", required=True), F("contact.title", "Their title or role"), F("contact.email", "Contact email", required=True), F("contact.phone", "Contact phone"),
    F("team.members", "The people who do the work (name, role, short bio): everyone counts, including you", "people", True, "This is the team the packet describes. It must be the real one."),
    F("team.contractors", "Subcontractors or partner firms you really use (name, what they do)", "people"),
    F("past_performance", "Past work you can point to (client, year, what was done, outcome)", "work", True, "Real engagements only. Clients can be named as references only with their consent."),
    F("financial.annual_revenue", "Annual revenue (optional)", "number"),
]
FIELD_BY_PATH = {f["path"]: f for f in FIELDS}


def _get(d, path):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def _set(d, path, v):
    ks = path.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    d[ks[-1]] = v


def _empty(v):
    return v is None or v == "" or v == [] or v == {}


def clean_value(field, v):
    k, label = field["kind"], field["label"]
    if _empty(v):
        return None
    if k in ("text", "textarea"):
        if not isinstance(v, str) or len(v) > 4000 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", v):
            raise DeskError("%s must be plain text up to 4000 characters" % label)
        return v.strip()
    if k == "number":
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")) or v < 0:
            raise DeskError("%s must be a number, 0 or more" % label)
        return v
    if k == "toggle":
        if not isinstance(v, bool):
            raise DeskError("%s must be true or false" % label)
        return v
    if k == "choice":
        if v not in field["choices"]:
            raise DeskError("%s must be one of: %s" % (label, ", ".join(field["choices"])))
        return v
    if k == "list":
        if isinstance(v, str):
            v = [x.strip() for x in v.split(",") if x.strip()]
        if not isinstance(v, list) or len(v) > 60 or not all(isinstance(x, str) and 0 < len(x) <= 200 for x in v):
            raise DeskError("%s must be a list of short items" % label)
        return v
    if k == "people":
        if not isinstance(v, list) or len(v) > 60 or not all(isinstance(x, dict) and str(x.get("name", "")).strip() and len(json.dumps(x)) < 2000 for x in v):
            raise DeskError("%s must be a list of {name, role, bio}" % label)
        return [{kk: str(vv)[:600] for kk, vv in x.items() if kk in ("name", "role", "bio", "does")} for x in v]
    if k == "work":
        if not isinstance(v, list) or len(v) > 60 or not all(isinstance(x, dict) and str(x.get("client", "")).strip() and str(x.get("summary", "")).strip() for x in v):
            raise DeskError("%s must be a list of {client, year, summary, outcome}" % label)
        return [{kk: str(vv)[:800] for kk, vv in x.items() if kk in ("client", "year", "summary", "outcome", "value")} for x in v]
    raise DeskError("unknown field kind")


class Vault:
    def __init__(self, path):
        self.path, self._lock = Path(path), threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {}
        if self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.path.replace(self.path.with_suffix(".corrupt-%d" % int(time.time())))        # never overwrite what could not be read
                self.data = {}

    def get(self, path):
        with self._lock:
            return _get(self.data, path)

    def update(self, facts):
        """facts: {path: value}. Every value is validated against its field; nothing is stored unless all are valid."""
        if not isinstance(facts, dict) or not facts:
            raise DeskError("give the facts to store as {path: value}")
        staged = {}
        for p, v in facts.items():
            if p not in FIELD_BY_PATH:
                raise DeskError("%r is not a vault field (fields: %s)" % (p, ", ".join(FIELD_BY_PATH)))
            staged[p] = clean_value(FIELD_BY_PATH[p], v)
        with self._lock:
            for p, v in staged.items():
                if v is None:
                    cur = self.data
                    ks = p.split(".")
                    for k in ks[:-1]:
                        cur = cur.get(k, {}) if isinstance(cur, dict) else {}
                    if isinstance(cur, dict):
                        cur.pop(ks[-1], None)
                else:
                    _set(self.data, p, v)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            return json.loads(json.dumps(self.data))

    def missing_required(self):
        return [f["path"] for f in FIELDS if f["required"] and _empty(self.get(f["path"]))]

    def headcount(self):
        m = self.get("team.members") or []
        c = self.get("team.contractors") or []
        return len(m), len(c)


# ---- opportunities ----
APPLICANT_RULES = {                                           # a funder's applicant type (lower-case fragment) -> the entity types it admits
    "501(c)(3)": ("nonprofit_501c3",), "do not have a 501(c)(3)": ("other_nonprofit",), "small business": ("small",), "for profit organizations other than small": ("llc", "s_corp", "c_corp", "partnership", "sole_proprietor"),
    "individuals": ("sole_proprietor",), "unrestricted": ("*",)}


def _applicant_types(opp):
    out = []
    for a in opp.get("applicant_types") or []:
        out.append(a if isinstance(a, str) else str(a.get("description") or a))
    return out


def check_eligibility(opp, vault):
    """-> {"verdict": "eligible"|"not_eligible"|"review", "reasons": [...]}. Never guesses: anything it cannot decide is 'review' with the reason."""
    et = vault.get("org.entity_type")
    if not et:
        return {"verdict": "review", "reasons": ["your entity type is not in the vault yet, so eligibility cannot be checked"]}
    types = [t.lower() for t in _applicant_types(opp)]
    text = (opp.get("eligibility_text") or "").lower()
    reasons, admits = [], False
    for t in types:
        for frag, who in APPLICANT_RULES.items():
            if frag in t:
                if "*" in who or et in who or (who == ("small",) and vault.get("org.small_business") is True and et not in ("nonprofit_501c3", "other_nonprofit")):
                    admits = True
                    reasons.append("the funder admits: %s" % t[:90])
        if t.startswith("others") or "see text" in t:
            reasons.append("the funder lists 'others': read its additional eligibility text")
            return {"verdict": "review", "reasons": reasons}
    if admits:
        if "501(c)(3)" in text and et != "nonprofit_501c3":
            return {"verdict": "review", "reasons": reasons + ["the eligibility text mentions 501(c)(3) status: confirm it applies to you"]}
        return {"verdict": "eligible", "reasons": reasons}
    if types:
        return {"verdict": "not_eligible", "reasons": ["none of the applicant types it admits (%s) includes %s" % ("; ".join(t[:60] for t in types[:4]), et.replace("_", " "))]}
    if "501(c)(3)" in text and et != "nonprofit_501c3":
        return {"verdict": "not_eligible", "reasons": ["the eligibility text asks for 501(c)(3) status"]}
    return {"verdict": "review", "reasons": ["no applicant types were given: read the funding notice's eligibility section"]}


def standard_requirements(opp):
    """The requirements the desk can check. Federal grants share a base set; the notice itself is the authority and the packet says so."""
    reqs = [{"id": "r-name", "text": "Legal name of the applicant", "kind": "field", "path": "org.legal_name"}, {"id": "r-type", "text": "Type of applicant", "kind": "field", "path": "org.entity_type"},
            {"id": "r-addr", "text": "Applicant address", "kind": "field", "path": "org.address"}, {"id": "r-contact", "text": "Authorised contact: name", "kind": "field", "path": "contact.name"},
            {"id": "r-email", "text": "Contact email", "kind": "field", "path": "contact.email"}, {"id": "r-mission", "text": "Organisation description", "kind": "field", "path": "org.mission"},
            {"id": "r-team", "text": "Key personnel", "kind": "field", "path": "team.members"}, {"id": "r-narr", "text": "Project narrative (written by you for this notice)", "kind": "document", "key": "narrative"},
            {"id": "r-budget", "text": "Budget: itemised, within the award range", "kind": "document", "key": "budget"}]
    desc = " ".join(str(opp.get(k) or "") for k in ("description", "eligibility_text", "title")).lower()
    if opp.get("source") == "grants.gov" or "sam.gov" in desc or "unique entity" in desc:
        reqs += [{"id": "r-uei", "text": "SAM.gov Unique Entity ID (you register yourself)", "kind": "field", "path": "org.uei"}]
    if re.search(r"past performance|track record|prior experience|relevant experience|demonstrated experience", desc):
        reqs.append({"id": "r-past", "text": "Past performance / relevant experience", "kind": "field", "path": "past_performance"})
    if "cost sharing" in desc or opp.get("cost_sharing") is True:
        reqs.append({"id": "r-cost", "text": "Cost-share or matching funds plan", "kind": "document", "key": "cost_share"})
    return reqs


def gap_analysis(opp, vault, answers=None):
    answers = answers or {}
    met, missing = [], []
    for r in opp.get("requirements") or standard_requirements(opp):
        if r["kind"] == "field":
            ok = not _empty(vault.get(r["path"]))
            (met if ok else missing).append(r)
        else:
            ok = not _empty((answers.get("documents") or {}).get(r["key"]))
            (met if ok else missing).append(r)
    questions = []
    for r in missing:
        if r["kind"] == "field":
            f = FIELD_BY_PATH[r["path"]]
            questions.append({"requirement": r["id"], "kind": "fact", "path": r["path"], "question": f["label"], "type": f["kind"], "help": f["help"], "choices": f.get("choices")})
        else:
            hint = {"narrative": "Write the project narrative for this notice (what you will do, for whom, how you will measure it, who does the work).", "budget": "Itemise the budget as lines of {item, amount}. The total must fall within the award range.",
                    "cost_share": "Describe the cost-share or matching funds, with sources."}.get(r["key"], r["text"])
            questions.append({"requirement": r["id"], "kind": "document", "key": r["key"], "question": r["text"], "type": "textarea" if r["key"] != "budget" else "budget", "help": hint})
    return {"met": [r["id"] for r in met], "missing": [r["id"] for r in missing], "questions": questions, "complete": not missing}


# ---- the claims check: the packet may not overstate the organisation ----
def claims_check(texts, vault):
    problems = []
    members, contractors = vault.headcount()
    people = members + contractors
    year = vault.get("org.year_founded")
    age = (datetime.date.today().year - int(year)) if year else None
    blob = "\n".join(t for t in texts if t)
    for m in re.finditer(r"(\d{1,5})\s*\+?\s*(?:full[- ]time\s+|dedicated\s+|in-house\s+|talented\s+|seasoned\s+|certified\s+)*" + STAFF_WORDS, blob, re.I):
        n = int(m.group(1))
        if n > people and n >= 2:
            problems.append("a text says %d %s but the vault lists %d people (%d on the team, %d contractors)" % (n, m.group(0).split()[-1], people, members, contractors))
    for m in re.finditer(r"team of (\d{1,5})", blob, re.I):
        if int(m.group(1)) > people:
            problems.append("a text says 'team of %s' but the vault lists %d people" % (m.group(1), people))
    if age is not None:
        for m in re.finditer(r"(\d{1,3})\s*\+?\s*years", blob, re.I):
            if int(m.group(1)) > age + 0 and int(m.group(1)) >= 2:
                problems.append("a text claims %s years but the organisation began in %s (%d years); personal experience belongs in a person's bio" % (m.group(1), year, age))
    for m in re.finditer(r"\b(offices? in|global network|worldwide presence|fortune\s*500|multinational|across \d+ (?:countries|offices))\b", blob, re.I):
        problems.append("the phrase %r implies a scale the vault does not record: remove it or record it as a fact first" % m.group(0))
    return problems


# ---- the desk ----
class Desk:
    def __init__(self, root, now=time.time, http=None):
        self.root, self.now = Path(root), now
        self.root.mkdir(parents=True, exist_ok=True)
        self.vault = Vault(self.root / "entity_vault.json")
        self._http, self._last_call, self._lock = http or self._urlopen, 0.0, threading.RLock()
        self.opps_dir = self.root / "opportunities"
        self.opps_dir.mkdir(exist_ok=True)
        self._ledger, self._last = self.root / "ledger.jsonl", "0" * 64
        try:
            lines = self._ledger.read_text(encoding="utf-8").strip().splitlines()
            self._last = json.loads(lines[-1])["hash"] if lines else self._last
        except (OSError, ValueError, KeyError, IndexError):
            pass

    # -- ledger
    def _log(self, event, detail=None):
        rec = {"t": round(self.now(), 3), "event": event, "detail": detail or {}, "prev": self._last}
        rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True).encode("utf-8")).hexdigest()
        with open(self._ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        self._last = rec["hash"]

    def verify_ledger(self):
        prev, n = "0" * 64, 0
        try:
            lines = self._ledger.read_text(encoding="utf-8").splitlines() if self._ledger.is_file() else []
        except OSError:
            return False, 0
        for n, line in enumerate(lines, 1):
            try:
                r = json.loads(line)
                h = r.pop("hash")
            except (ValueError, KeyError):
                return False, n
            if r.get("prev") != prev or hashlib.sha256(json.dumps(r, sort_keys=True).encode("utf-8")).hexdigest() != h:
                return False, n
            prev = h
        return True, n

    # -- the one network door (official API only, one request at a time, rate limited)
    @staticmethod
    def _urlopen(url, body):
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": USER_AGENT}, method="POST")
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read(4 * 1024 * 1024).decode("utf-8"))

    def _call(self, url, body):
        if not url.startswith("https://api.grants.gov/"):
            raise DeskError("only the official Grants.gov API is used for discovery")
        with self._lock:
            wait = MIN_GAP_S - (self.now() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = self.now()
            try:
                d = self._http(url, body)
            except (urllib.error.URLError, OSError, ValueError) as e:
                raise DeskError("Grants.gov did not answer: %s" % e)
        if not isinstance(d, dict) or d.get("errorcode") not in (0, "0", None):
            raise DeskError("Grants.gov refused the request: %s" % (d.get("msg") if isinstance(d, dict) else "unreadable answer"))
        return d.get("data") or {}

    def search(self, keyword, rows=10, statuses="forecasted|posted"):
        keyword = str(keyword or "").strip()
        if not keyword or len(keyword) > 120:
            raise DeskError("give a search word or phrase (up to 120 characters)")
        rows = max(1, min(int(rows), 25))
        data = self._call(GRANTS_SEARCH, {"rows": rows, "keyword": keyword, "oppStatuses": statuses})
        hits = [{"id": str(h.get("id")), "number": h.get("number"), "title": h.get("title"), "agency": h.get("agency"), "open_date": h.get("openDate"), "close_date": h.get("closeDate"),
                 "status": h.get("oppStatus")} for h in data.get("oppHits", [])]
        self._log("search", {"keyword": keyword, "hits": len(hits), "total": data.get("hitCount")})
        return {"hits": hits, "total": data.get("hitCount")}

    def fetch(self, opp_id):
        opp_id = re.sub(r"[^0-9]", "", str(opp_id))
        if not opp_id:
            raise DeskError("a Grants.gov opportunity id is a number")
        d = self._call(GRANTS_DETAIL, {"opportunityId": int(opp_id)})
        s = d.get("synopsis") or {}
        types = s.get("applicantTypes") or []
        if isinstance(types, str):
            try:
                import ast
                types = ast.literal_eval(types)
            except (ValueError, SyntaxError):
                types = [types]
        opp = {"id": "gg-" + opp_id, "source": "grants.gov", "number": d.get("opportunityNumber"), "title": d.get("opportunityTitle"), "agency": s.get("agencyName") or d.get("owningAgencyCode"),
               "open_date": s.get("postingDate"), "close_date": s.get("responseDate"), "award_floor": _num(s.get("awardFloor")), "award_ceiling": _num(s.get("awardCeiling")),
               "cost_sharing": str(s.get("costSharing")).lower() == "true", "applicant_types": [t.get("description") if isinstance(t, dict) else str(t) for t in types],
               "eligibility_text": s.get("applicantEligibilityDesc") or "", "description": s.get("synopsisDesc") or "", "url": "https://www.grants.gov/search-results-detail/" + opp_id,
               "contact": {"name": s.get("agencyContactName"), "email": s.get("agencyContactDesc"), "phone": s.get("agencyContactPhone")}, "fetched_at": round(self.now(), 3)}
        self._save_opp(opp)
        self._log("fetched", {"id": opp["id"], "title": (opp["title"] or "")[:80]})
        return opp

    def add_manual(self, opp):
        for k in ("title", "agency"):
            if not str(opp.get(k) or "").strip():
                raise DeskError("an opportunity needs a %s" % k)
        o = {"id": "m-" + uuid.uuid4().hex[:10], "source": "manual", "title": str(opp["title"])[:200], "agency": str(opp["agency"])[:200], "number": str(opp.get("number") or "")[:60],
             "close_date": str(opp.get("close_date") or "")[:40], "award_floor": _num(opp.get("award_floor")), "award_ceiling": _num(opp.get("award_ceiling")), "cost_sharing": bool(opp.get("cost_sharing")),
             "applicant_types": [str(x)[:200] for x in (opp.get("applicant_types") or [])][:20], "eligibility_text": str(opp.get("eligibility_text") or "")[:4000], "description": str(opp.get("description") or "")[:8000],
             "url": str(opp.get("url") or "")[:400], "fetched_at": round(self.now(), 3)}
        reqs = opp.get("requirements")
        if reqs is not None:
            o["requirements"] = _clean_reqs(reqs)
        self._save_opp(o)
        self._log("added_manual", {"id": o["id"], "title": o["title"][:80]})
        return o

    # -- storage of opportunities and their working state (answers, sign-off)
    def _path(self, oid):
        if not re.fullmatch(r"(gg|m)-[0-9a-f]{1,12}|gg-\d{1,12}", oid):
            raise DeskError("not a valid opportunity id")
        return self.opps_dir / oid

    def _save_opp(self, opp):
        d = self._path(opp["id"])
        d.mkdir(exist_ok=True)
        tmp = d / "opportunity.tmp"
        tmp.write_text(json.dumps(opp, indent=1), encoding="utf-8")
        os.replace(tmp, d / "opportunity.json")

    def get(self, oid):
        p = self._path(oid) / "opportunity.json"
        if not p.is_file():
            raise DeskError("no such opportunity: fetch or add it first")
        return json.loads(p.read_text(encoding="utf-8"))

    def list(self):
        out = []
        for d in sorted(self.opps_dir.iterdir()):
            p = d / "opportunity.json"
            if p.is_file():
                try:
                    o = json.loads(p.read_text(encoding="utf-8"))
                    out.append({k: o.get(k) for k in ("id", "title", "agency", "close_date", "source")})
                except ValueError:
                    continue
        return out

    def _state(self, oid):
        p = self._path(oid) / "state.json"
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                pass
        return {"answers": {"documents": {}}, "signoff": None}

    def _save_state(self, oid, st):
        p = self._path(oid)
        tmp = p / "state.tmp"
        tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
        os.replace(tmp, p / "state.json")

    def analyze(self, oid):
        opp, st = self.get(oid), self._state(oid)
        return {"opportunity": opp, "eligibility": check_eligibility(opp, self.vault), "gap": gap_analysis(opp, self.vault, st["answers"]), "signed_off": bool(st.get("signoff")),
                "vault_missing_required": self.vault.missing_required()}

    def answer(self, oid, facts=None, documents=None):
        """Store what the questionnaire asked for: facts go into the vault, documents (narrative, budget) are kept with this opportunity."""
        opp, st = self.get(oid), self._state(oid)
        if facts:
            self.vault.update(facts)
        for k, v in (documents or {}).items():
            if k == "budget":
                st["answers"]["documents"][k] = _clean_budget(v, opp)
            elif k in ("narrative", "cost_share"):
                if not isinstance(v, str) or len(v) > 30000:
                    raise DeskError("%s must be text up to 30000 characters" % k)
                st["answers"]["documents"][k] = v.strip()
            else:
                raise DeskError("unknown document %r" % k)
        st["signoff"] = None                                       # anything changed: an earlier sign-off no longer covers it
        self._save_state(oid, st)
        self._log("answered", {"id": oid, "facts": sorted(facts or {}), "documents": sorted(documents or {})})
        return self.analyze(oid)

    SIGNOFF_TEXT = ("I confirm that every statement in this application packet is accurate, that it describes my organisation as it really is, and that I will review it and submit it myself "
                    "through the funder's official process.")

    def sign_off(self, oid, name, confirm):
        a = self.analyze(oid)
        if not a["gap"]["complete"]:
            raise DeskError("answer the open questions first (%d missing)" % len(a["gap"]["missing"]))
        if confirm is not True or not str(name or "").strip():
            raise DeskError("sign-off needs your name and an explicit confirmation of the statement")
        st = self._state(oid)
        st["signoff"] = {"name": str(name).strip()[:120], "statement": self.SIGNOFF_TEXT, "at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.now())),
                         "inputs_sha256": self._inputs_hash(oid)}
        self._save_state(oid, st)
        self._log("signed_off", {"id": oid, "by": st["signoff"]["name"], "inputs_sha256": st["signoff"]["inputs_sha256"]})
        return st["signoff"]

    def _inputs_hash(self, oid):
        st = self._state(oid)
        blob = json.dumps({"vault": self.vault.snapshot(), "opp": self.get(oid), "docs": st["answers"]}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # -- compile
    def compile(self, oid):
        a = self.analyze(oid)
        st = self._state(oid)
        so = st.get("signoff")
        if not so:
            raise DeskError("compile needs your sign-off first")
        if so["inputs_sha256"] != self._inputs_hash(oid):
            raise DeskError("something changed after you signed off: sign off again on the current version")
        if a["eligibility"]["verdict"] == "not_eligible":
            raise DeskError("the organisation does not appear eligible: %s" % "; ".join(a["eligibility"]["reasons"]))
        if not a["gap"]["complete"] or a["vault_missing_required"]:
            raise DeskError("the vault or the answers are incomplete: %s" % ", ".join(a["vault_missing_required"] or a["gap"]["missing"]))
        opp, v, docs = a["opportunity"], self.vault.snapshot(), st["answers"]["documents"]
        texts = [docs.get("narrative"), docs.get("cost_share"), _get(v, "org.mission")] + [p.get("bio") for p in (_get(v, "team.members") or [])] + [w.get("summary") for w in (_get(v, "past_performance") or [])]
        problems = claims_check(texts, self.vault)
        if problems:
            self._log("compile_blocked", {"id": oid, "problems": problems})
            raise DeskError("the claims check blocked the packet: " + " | ".join(problems))
        out = self.root / "packets" / (oid + "-" + time.strftime("%Y%m%d-%H%M%S", time.localtime(self.now())))
        out.mkdir(parents=True)
        files = _render_packet(opp, v, docs, so, a["eligibility"])
        manifest = {"opportunity": {k: opp.get(k) for k in ("id", "title", "agency", "number", "close_date", "url")}, "prepared_for_submission_by": _get(v, "org.legal_name"), "signed_off_by": so["name"],
                    "signed_off_at": so["at"], "claims_check": "passed", "team_described": {"members": len(_get(v, "team.members") or []), "contractors": len(_get(v, "team.contractors") or [])},
                    "not_included": ["Official forms (for Grants.gov: complete the SF-424 family in Grants.gov Workspace)", "EIN, SSN, bank or card details (entered at the funder's portal only)", "SAM.gov registration (you do this yourself)"],
                    "files": {}}
        for name, text in files.items():
            (out / name).write_bytes(text.encode("utf-8"))                       # bytes, so the file is exactly what was hashed (no newline translation on Windows)
            manifest["files"][name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        (out / "manifest.json").write_bytes(json.dumps(manifest, indent=1).encode("utf-8"))
        self._log("compiled", {"id": oid, "packet": out.name, "files": len(files)})
        return {"packet": out.name, "files": sorted(files) + ["manifest.json"], "manifest": manifest}

    def packet_file(self, packet, name):
        if not re.fullmatch(r"(gg|m)-[0-9a-f]{1,12}-\d{8}-\d{6}", packet) or not re.fullmatch(r"[a-z_]+\.(md|html|json)", name):
            raise DeskError("not a packet file")
        p = (self.root / "packets" / packet / name).resolve()
        if (self.root / "packets").resolve() not in p.parents or not p.is_file():
            raise DeskError("no such packet file")
        return p


def _num(v):
    try:
        f = float(str(v).replace(",", ""))
        return f if f == f and f >= 0 else None
    except (TypeError, ValueError):
        return None


def _clean_reqs(reqs):
    out = []
    for i, r in enumerate(reqs if isinstance(reqs, list) else []):
        if not isinstance(r, dict) or not str(r.get("text", "")).strip():
            raise DeskError("requirement %d needs text" % (i + 1))
        k = r.get("kind")
        if k == "field" and r.get("path") in FIELD_BY_PATH:
            out.append({"id": "r-%d" % (i + 1), "text": str(r["text"])[:300], "kind": "field", "path": r["path"]})
        elif k == "document" and re.fullmatch(r"[a-z_]{2,30}", str(r.get("key", ""))) and r["key"] in ("narrative", "budget", "cost_share"):
            out.append({"id": "r-%d" % (i + 1), "text": str(r["text"])[:300], "kind": "document", "key": r["key"]})
        else:
            raise DeskError("requirement %d: kind 'field' needs a vault path (%s) and kind 'document' needs a key of narrative, budget or cost_share" % (i + 1, ", ".join(list(FIELD_BY_PATH)[:5]) + ", ..."))
    return out


def _clean_budget(v, opp):
    if not isinstance(v, list) or not v or len(v) > 100:
        raise DeskError("the budget is a list of 1 to 100 lines of {item, amount}")
    lines, total = [], 0.0
    for i, ln in enumerate(v):
        amt = _num(ln.get("amount")) if isinstance(ln, dict) else None
        if not isinstance(ln, dict) or not str(ln.get("item", "")).strip() or amt is None:
            raise DeskError("budget line %d needs an item and an amount (a number, 0 or more)" % (i + 1))
        lines.append({"item": str(ln["item"]).strip()[:200], "amount": round(amt, 2)})
        total += amt
    lo, hi = opp.get("award_floor"), opp.get("award_ceiling")
    if hi and total > hi:
        raise DeskError("the budget totals %.2f, over the award ceiling of %.2f" % (total, hi))
    if lo and total < lo:
        raise DeskError("the budget totals %.2f, under the award floor of %.2f" % (total, lo))
    return lines


# ---- the packet: complete, plain and accurate ----
CSS = ("body{font:15px/1.55 Georgia,'Times New Roman',serif;max-width:820px;margin:40px auto;padding:0 20px;color:#1b1f2a}h1{font-size:1.7rem;border-bottom:3px solid #1d4ed8;padding-bottom:6px}"
       "h2{font-size:1.2rem;margin-top:2em;color:#1d4ed8}table{border-collapse:collapse;width:100%}td,th{border:1px solid #cbd5e1;padding:6px 10px;text-align:left}th{background:#f1f5f9}"
       ".note{background:#fff7ed;border-left:4px solid #f59e0b;padding:8px 12px;margin:1em 0}@media print{h2{page-break-after:avoid}}")


def _md_to_html(md):
    out, in_list = [], False
    for ln in md.splitlines():
        if ln.startswith("# "):
            out.append("<h1>%s</h1>" % html.escape(ln[2:]))
        elif ln.startswith("## "):
            out.append("<h2>%s</h2>" % html.escape(ln[3:]))
        elif ln.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>%s</li>" % html.escape(ln[2:]))
            continue
        elif ln.startswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            out.append("<tr>%s</tr>" % "".join("<td>%s</td>" % html.escape(c) for c in cells))
        elif ln.strip():
            out.append("<p>%s</p>" % html.escape(ln))
        if in_list and not ln.startswith("- "):
            out.append("</ul>")
            in_list = False
    if in_list:
        out.append("</ul>")
    body = "\n".join(out).replace("<tr>", "<table><tr>", 1) if "<tr>" in "\n".join(out) else "\n".join(out)
    return body + ("</table>" if "<table>" in body else "")


def _render_packet(opp, v, docs, so, elig):
    org = _get(v, "org.legal_name")
    members, contractors = _get(v, "team.members") or [], _get(v, "team.contractors") or []
    total = sum(l["amount"] for l in docs.get("budget", []))
    today = so["at"][:10]
    team_line = ("%s is run by %s." % (org, _join([m["name"] for m in members]))) if len(members) > 1 else ("%s is a one-person practice run by %s." % (org, members[0]["name"]))
    cover = "\n".join(["# Cover letter", "", "%s" % today, "", "To: %s" % opp.get("agency"), "Re: " + " ".join(x for x in (opp.get("number"), opp.get("title")) if x), "",
                       "%s applies under the above opportunity. %s" % (org, team_line),
                       "", "%s" % _get(v, "org.mission"), "", "The requested amount is %.2f, itemised in the attached budget." % total, "",
                       "Contact: %s%s, %s%s" % (_get(v, "contact.name"), (", " + _get(v, "contact.title")) if _get(v, "contact.title") else "", _get(v, "contact.email"), (", " + _get(v, "contact.phone")) if _get(v, "contact.phone") else ""), "",
                       "Sincerely,", _get(v, "contact.name")]) + "\n"
    profile = "\n".join(["# Organisation profile", "", "- Legal name: %s" % org, "- Entity type: %s" % str(_get(v, "org.entity_type")).replace("_", " "), "- Formed in: %s, %s" % (_get(v, "org.state"), _get(v, "org.year_founded")),
                         "- Address: %s" % _get(v, "org.address")] + (["- Website: %s" % _get(v, "org.website")] if _get(v, "org.website") else []) + (["- SAM.gov UEI: %s" % _get(v, "org.uei")] if _get(v, "org.uei") else [])
                        + (["- NAICS: %s" % ", ".join(_get(v, "org.naics"))] if _get(v, "org.naics") else []) + (["- Certifications: %s" % ", ".join(_get(v, "org.certifications"))] if _get(v, "org.certifications") else [])
                        + ["", "## What we do", "", _get(v, "org.mission"), ""] + ["- %s" % s for s in (_get(v, "org.services") or [])]) + "\n"
    personnel = "\n".join(["# Key personnel", "", ("One person does the work." if len(members) == 1 else "%d people do the work." % len(members)), ""] + sum([["## %s%s" % (m["name"], (" - " + m["role"]) if m.get("role") else ""), "", m.get("bio") or "", ""] for m in members], [])
                          + (["## Subcontractors and partners", ""] + ["- %s: %s" % (c["name"], c.get("does") or c.get("role") or "") for c in contractors] if contractors else [])) + "\n"
    past = "\n".join(["# Past performance", ""] + sum([["## %s%s" % (w["client"], (" (%s)" % w["year"]) if w.get("year") else ""), "", w["summary"], ("Outcome: %s" % w["outcome"]) if w.get("outcome") else "", ""] for w in (_get(v, "past_performance") or [])], [])) + "\n"
    budget = "\n".join(["# Budget", "", "| Item | Amount |", "|---|---|"] + ["| %s | %.2f |" % (l["item"], l["amount"]) for l in docs["budget"]] + ["| **Total** | **%.2f** |" % total]
                       + ([] if not (opp.get("award_floor") or opp.get("award_ceiling")) else ["", "Award range stated by the funder: %s to %s." % (opp.get("award_floor") or "n/a", opp.get("award_ceiling") or "n/a")])) + "\n"
    narrative = "# Project narrative\n\n" + docs["narrative"] + "\n"
    if docs.get("cost_share"):
        narrative += "\n## Cost share\n\n" + docs["cost_share"] + "\n"
    attest = "\n".join(["# Attestations and checklist", "", "Signed off by %s on %s with this statement:" % (so["name"], so["at"]), "", "> " + so["statement"], "", "## Before you submit (you do these yourself)", "",
                        "- Read every page of the funding notice and compare it with this packet.", "- Complete the funder's official forms in their own system.", "- Enter identifiers such as EIN and bank details at the funder's portal; they are not stored here.",
                        "- Confirm registrations the funder requires (for federal awards: SAM.gov).", "- Check the deadline: %s" % (opp.get("close_date") or "see the notice"), "- Eligibility check result: %s (%s)" % (elig["verdict"], "; ".join(elig["reasons"])), ""]) + "\n"
    howto = "\n".join(["# Submission notes", "", "This packet was prepared for you to submit. Nothing has been sent anywhere and nothing will be sent automatically.", "",
                       "1. Review each file in this folder.", "2. Open the funding notice: %s" % (opp.get("url") or "(from the funder)"), "3. Submit through the funder's official portal, under your own name and identity.", ""]) + "\n"
    files = {"cover_letter.md": cover, "organization_profile.md": profile, "key_personnel.md": personnel, "past_performance.md": past, "budget.md": budget, "project_narrative.md": narrative, "attestations_checklist.md": attest, "submission_notes.md": howto}
    combined = "\n\n".join(files[k] for k in ("cover_letter.md", "organization_profile.md", "project_narrative.md", "budget.md", "key_personnel.md", "past_performance.md", "attestations_checklist.md"))
    files["application_packet.html"] = "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>%s</title><style>%s</style></head><body>%s</body></html>" % (html.escape("%s - %s" % (org, opp.get("title") or "")), CSS, _md_to_html(combined))
    return files


def _join(names):
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else (names[0] if names else "")
