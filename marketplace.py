"""marketplace.py - the NEXXUS Marketplace: a buyer storefront, and a creator portal where every product must survive a vetting gauntlet before it can be listed.

Two views of one marketplace
  buyer    the storefront: published, vetted products only, with category filters, search, sorting and any discount the administrator has set. Built by public_catalog(), the one place that decides
           what a visitor may see (no drafts, no reviews, no agreements, no creator details beyond the listing).
  creator  a micro-company submits a product and follows it through the gauntlet below.

The gauntlet (strict order, nothing can be skipped)
  1 intake      AUTO      the bundle is a safe zip with a valid manifest (the AXIS intake standards: nothing is executed, paths stay inside, every file parses, explicit names)
  2 hygiene     AUTO      no executables, no oversized files, no secrets or private paths
  3 security    AUTO      static analysis of the code: dangerous constructs are blocked, and what the code can DO (network, files, subprocess, environment) must match what the manifest declares
  4 listing     AUTO      honest listing: complete, a recognised licence, a real README, no income guarantees
  5 functional  REVIEWER  functional and stress tests run by a person in an ISOLATED environment, attested with a test report
  6 review      ADMIN     a reviewer's checklist and sign-off
  7 agreement   CREATOR   the partnership agreement (including the platform's revenue share) is signed
  8 greenlight  ADMIN     the administrator publishes it, and sets the checkout link

Why the stress test is not automatic: NEXXUS never executes submitted code on this computer. Without a real sandbox (no network, no filesystem access, resource limits) running a stranger's code is exactly how
machines get compromised, so stages 1-4 only READ the bundle, and stage 5 is done by a person in a disposable environment who attaches the report. The storefront says which checks were automatic and which were
attested by a person.

Not handled here: payments. The Buy button opens a checkout link the administrator sets (for example a payment provider's hosted checkout); NEXXUS never sees card details. The revenue share is recorded in the agreement,
but software cannot enforce it: payouts and taxes need a payment provider that can split and settle funds, and a lawyer-reviewed agreement. Do not sell until both are in place.
"""
import ast
import hashlib
import io
import json
import os
import re
import threading
import time
import uuid
import zipfile

import market_social as social
import seo
import teams

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "nexxus_data", "marketplace")
SUBS_PATH = os.path.join(DATA_DIR, "submissions.json")
BLOB_DIR = os.path.join(DATA_DIR, "quarantine")
AUDIT_PATH = os.path.join(DATA_DIR, "audit.jsonl")
REPORTS_PATH = os.path.join(DATA_DIR, "reports.jsonl")
_LOCK = threading.RLock()

MAX_ZIP = 5 * 1024 * 1024
MAX_ENTRIES = 300
MAX_UNCOMPRESSED = 25 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
REVENUE_SHARE_PERCENT = 5

CATEGORIES = ("Software", "Templates", "Guides", "Assets", "Automation", "Scripts", "Tools", "Trinkets")
KINDS = ("software", "template", "guide", "asset", "automation")
PERMISSIONS = ("network", "files", "subprocess", "env")
LICENSES = ("MIT", "Apache-2.0", "BSD-3-Clause", "GPL-3.0", "MPL-2.0", "CC-BY-4.0", "CC0-1.0", "Proprietary")
FOSS_LICENSES = ("MIT", "Apache-2.0", "BSD-3-Clause", "ISC", "GPL-3.0", "LGPL-3.0", "AGPL-3.0", "MPL-2.0", "Unlicense", "CC0-1.0")       # the Free & Open tier accepts open-source licences only
TIERS = ("commercial", "free")
FREE_ACKS = ("licence_right", "no_malware", "conduct")
FREE_DECLARATION = """CONTRIBUTION DECLARATION: FREE AND OPEN TIER

By signing I confirm that: (1) I wrote this code or have the right to share it under the open-source licence stated in my bundle, and the LICENSE file matches it; (2) it contains no malware, hidden behaviour or credentials, and does what its README says; (3) I agree to the NEXXUS Code of Conduct. I understand that anyone can read and download it, that the automatic checks and an administrator's approval are not a guarantee of safety, and that the Marketplace may remove it at any time. This tier has no payments and no revenue share."""
FREE_DECLARATION_SHA = hashlib.sha256(FREE_DECLARATION.encode("utf-8")).hexdigest()
MAX_VIEW = 200 * 1024
TEXT_EXT = {".py", ".js", ".mjs", ".json", ".md", ".txt", ".html", ".css", ".csv", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".svg", ".sh", ".ps1", ".bat", ".sql", ".xml", ".rst"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}
TEXT_NAMES = {"license", "licence", "copying", "notice", "authors", "readme", "changelog", "unlicense", "contributing", "codeowners"}       # well-known text files that have no extension


def _is_text(name):
    base = os.path.basename(name.lower())
    return os.path.splitext(base)[1] in TEXT_EXT or base in TEXT_NAMES


BLOCKED_EXT = {".exe", ".dll", ".msi", ".scr", ".com", ".so", ".dylib", ".jar", ".class", ".apk", ".app", ".bin", ".pyc", ".pyd", ".vbs", ".lnk", ".zip", ".7z", ".rar", ".gz", ".tar"}
DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}
PLACEHOLDER_NAMES = {"temp", "test", "untitled", "new", "project", "my-project", "myproject", "app", "demo", "sample"}
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

SECRET_PATTERNS = (
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Stripe live key", re.compile(r"\b[sr]k_live_[0-9a-zA-Z]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("hard-coded credential", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|passw(?:or)?d)\b\s*[:=]\s*[\"'][^\"'\s]{16,}[\"']")),
)
PRIVATE_PATH = re.compile(r"[A-Za-z]:[\\/]Users[\\/]|/home/[a-z0-9_-]+/|/Users/[A-Za-z0-9_-]+/")
EARNINGS_CLAIMS = re.compile(r"(?i)\bguaranteed\b|\bget rich\b|\bpassive income\b|\bmake \$?\d|\bearn \$?\d|\bovernight success\b|\b100% (?:safe|secure|risk[- ]free)\b")

AGREEMENT_VERSION = "2026-10-draft"
AGREEMENT_TEXT = """NEXXUS MARKETPLACE PARTNERSHIP AGREEMENT (version %s)

DRAFT TEMPLATE. This is a plain-language starting point, not legal advice. Have a lawyer review and complete it before real sales begin.

1. Listing and licence. You ("Creator") ask the NEXXUS Marketplace operator ("Platform") to list and distribute the product you submitted. You grant the Platform a non-exclusive right to list, display, host and deliver it to buyers on the terms you chose in your listing. You keep ownership of your product.

2. Revenue share. For every sale made through the Marketplace, the Platform keeps %d%% of the net revenue and pays the remaining %d%% to you. Net revenue means the price the buyer paid, excluding taxes collected and amounts refunded. Payment-processor fees are handled as set out in the checkout arrangement, which the Platform will show you before your first sale. Payouts follow the Platform's payout schedule.

3. Originality and safety. You promise that you made the product or have the right to sell it, that it contains no malware or hidden behaviour, that it does what the listing says, and that it does not infringe anyone's rights. Everything you submitted passed the Platform's vetting only on the basis of what you declared; if that was untrue, the listing may be removed.

4. Quality, support and refunds. You will fix serious defects promptly, answer buyer questions in good faith, and honour the refund terms shown on your listing.

5. Removal. The Platform may remove a listing at any time, for example for a security problem, a rights complaint, a breach of the Code of Conduct or a failed re-check. You may withdraw a listing; existing buyers keep what they bought.

6. No guarantees. The Platform does not promise any number of sales or any income.

7. Changes and law. Updates to your product go through the same vetting. Governing law and dispute handling: [to be completed with legal counsel].

By signing, you confirm you have read and agree to this agreement, including the %d%% revenue share.""" % (AGREEMENT_VERSION, REVENUE_SHARE_PERCENT, 100 - REVENUE_SHARE_PERCENT, REVENUE_SHARE_PERCENT)
AGREEMENT_SHA = hashlib.sha256(AGREEMENT_TEXT.encode("utf-8")).hexdigest()
AGREEMENT_ACKS = ("read", "revenue_share", "originality")

STAGES = (("intake", "Intake and manifest", "auto"), ("hygiene", "File hygiene and secrets", "auto"), ("security", "Static security validation", "auto"), ("listing", "Honest listing", "auto"),
          ("functional", "Functional and stress tests (isolated, reviewer-run)", "reviewer"), ("review", "Reviewer sign-off", "admin"), ("agreement", "Partnership agreement", "creator"),
          ("greenlight", "Administrator greenlight", "admin"))
FREE_STAGES = STAGES[:4] + (("declaration", "Contribution declaration", "creator"), ("approval", "Administrator approval", "admin"))
REVIEW_CHECKLIST = ("listing_honest", "no_misleading_claims", "licence_ok", "security_findings_reviewed", "tested_in_isolation", "content_pg13", "no_third_party_ip_issue")


class MarketError(ValueError):
    pass


# ---------------------------------------------------------------- storage
def _clean(s, n):
    return _CTRL.sub("", str(s or "")).strip()[:n]


def _read():
    try:
        with open(SUBS_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _write(subs):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SUBS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(subs, f)
    os.replace(tmp, SUBS_PATH)


def _audit(sid, actor, action, detail=""):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time()), "id": sid, "actor": actor, "action": action, "detail": _clean(detail, 200)}) + "\n")
    except OSError:
        pass


def audit(limit=200):
    out = []
    try:
        with open(AUDIT_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return list(reversed(out))[:limit]


def _find(subs, sid):
    s = next((x for x in subs if x["id"] == str(sid)), None)
    if not s:
        raise MarketError("No such submission.")
    return s


# ---------------------------------------------------------------- the safe reader for the bundle (nothing is extracted to disk and nothing is executed)
def _safe_name(name):
    n = name.replace("\\", "/")
    if not n or n.startswith("/") or re.match(r"^[A-Za-z]:", n) or any(p in ("..", "") for p in n.rstrip("/").split("/")):
        return None
    if any(p.split(".")[0].upper() in DEVICE_NAMES for p in n.split("/")):
        return None
    return n


def read_bundle(data):
    """-> (files {name: bytes}, findings). A zip that is unsafe is rejected outright with a reason."""
    if not data or len(data) > MAX_ZIP:
        raise MarketError("The bundle must be a .zip of at most %d MB." % (MAX_ZIP // 1048576))
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise MarketError("That is not a valid .zip file.")
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if not infos or len(infos) > MAX_ENTRIES:
        raise MarketError("The bundle must hold between 1 and %d files." % MAX_ENTRIES)
    if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
        raise MarketError("The bundle expands to more than %d MB." % (MAX_UNCOMPRESSED // 1048576))
    files = {}
    for i in infos:
        name = _safe_name(i.filename)
        if not name:
            raise MarketError("An entry has an unsafe path: paths must stay inside the bundle (no '..', absolute paths, drive letters or device names).")
        if (i.external_attr >> 16) & 0o170000 == 0o120000:
            raise MarketError("The bundle contains a symbolic link (%s), which is not allowed." % name)
        if i.flag_bits & 0x1:
            raise MarketError("The bundle contains an encrypted file (%s); NEXXUS cannot inspect it." % name)
        if i.file_size > MAX_FILE:
            raise MarketError("%s is larger than %d MB." % (name, MAX_FILE // 1048576))
        if i.compress_size and i.file_size / max(1, i.compress_size) > 200 and i.file_size > 1024 * 1024:
            raise MarketError("%s looks like a compression bomb." % name)
        with zf.open(i) as fh:
            body = fh.read(MAX_FILE + 1)
        if len(body) > MAX_FILE:
            raise MarketError("%s is larger than %d MB." % (name, MAX_FILE // 1048576))
        if name in files:
            raise MarketError("Duplicate entry: %s." % name)
        files[name] = body
    return files


# ---------------------------------------------------------------- stage 1: intake
def _manifest(files):
    raw = files.get("marketplace.json")
    if raw is None:
        return None, [("block", "marketplace.json", 0, "The bundle needs a marketplace.json manifest at its top level.")]
    try:
        m = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, [("block", "marketplace.json", 0, "marketplace.json is not valid JSON.")]
    if not isinstance(m, dict):
        return None, [("block", "marketplace.json", 0, "marketplace.json must be a JSON object.")]
    f = []
    name = str(m.get("name", "")).strip()
    if not name or len(name) > 60 or name.lower() in PLACEHOLDER_NAMES:
        f.append(("block", "marketplace.json", 0, "The product needs an explicit name (not a placeholder like 'temp' or 'test'), up to 60 characters."))
    if not _SEMVER.match(str(m.get("version", ""))):
        f.append(("block", "marketplace.json", 0, "version must look like 1.0.0."))
    d = str(m.get("description", "")).strip()
    if not 40 <= len(d) <= 600:
        f.append(("block", "marketplace.json", 0, "description must be 40 to 600 characters."))
    if m.get("kind") not in KINDS:
        f.append(("block", "marketplace.json", 0, "kind must be one of: " + ", ".join(KINDS) + "."))
    perms = m.get("permissions", [])
    if not isinstance(perms, list) or any(p not in PERMISSIONS for p in perms):
        f.append(("block", "marketplace.json", 0, "permissions must be a list drawn from: " + ", ".join(PERMISSIONS) + "."))
    entry = m.get("entry")
    if not isinstance(entry, str) or _safe_name(entry) not in files:
        f.append(("block", "marketplace.json", 0, "entry must name a file that is in the bundle."))
    return m, f


def stage_intake(files):
    m, findings = _manifest(files)
    for name, body in files.items():                                   # every file that can be parsed must parse (the AXIS intake rule)
        low = name.lower()
        try:
            if low.endswith(".py"):
                ast.parse(body.decode("utf-8", "strict"), filename=name)
            elif low.endswith(".json"):
                json.loads(body.decode("utf-8", "strict"))
        except SyntaxError as e:
            findings.append(("block", name, e.lineno or 0, "Python does not parse: %s." % (e.msg or "syntax error")))
        except (ValueError, UnicodeDecodeError):
            findings.append(("block", name, 0, "The file is not valid %s." % ("JSON" if low.endswith(".json") else "UTF-8 text")))
    return findings, m


# ---------------------------------------------------------------- stage 2: hygiene
def _is_native_binary(body):
    return body[:2] == b"MZ" or body[:4] == b"\x7fELF" or body[:4] in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe") or body[:2] == b"PK"


def stage_hygiene(files):
    f = []
    for name, body in sorted(files.items()):
        ext = os.path.splitext(name.lower())[1]
        if ext in BLOCKED_EXT or _is_native_binary(body):
            f.append(("block", name, 0, "Executables, compiled code and nested archives are not accepted."))
            continue
        if not _is_text(name) and ext not in IMAGE_EXT:
            f.append(("block", name, 0, "File type %s is not accepted (allowed: text, code, documents and images)." % (ext or "(none)")))
            continue
        if os.path.basename(name).lower() in (".env", ".env.local", "id_rsa", "id_ed25519", ".npmrc", ".pypirc", "credentials.json"):
            f.append(("block", name, 0, "This looks like a credentials file and must not be in a bundle."))
        if _is_text(name):
            text = body.decode("utf-8", "replace")
            for i, line in enumerate(text.splitlines(), 1):
                if len(line) > 5000:
                    f.append(("warn", name, i, "A very long line (possible minified or obfuscated code); a reviewer will look at it."))
                    break
            for label, rx in SECRET_PATTERNS:
                for m in rx.finditer(text):
                    f.append(("block", name, text.count("\n", 0, m.start()) + 1, "A %s appears to be in the file (it is not shown here). Remove it and rotate it." % label))
                    break
            m = PRIVATE_PATH.search(text)
            if m:
                f.append(("warn", name, text.count("\n", 0, m.start()) + 1, "A personal file path appears in the file."))
    return f


# ---------------------------------------------------------------- stage 3: static security
NET_MODULES = {"requests", "urllib", "http", "socket", "aiohttp", "httpx", "ftplib", "smtplib", "websockets", "websocket", "telnetlib", "xmlrpc"}
SUB_MODULES = {"subprocess", "pty", "multiprocessing", "asyncio.subprocess"}
BLOCKED_MODULES = {"ctypes", "marshal", "pickle", "cPickle", "shelve", "dill", "imp"}
BLOCKED_CALLS = {"eval", "exec", "compile", "__import__"}
FILE_CALLS = {"remove", "unlink", "rmdir", "removedirs", "rmtree", "rename", "replace", "chmod", "write_text", "write_bytes", "copy", "copy2", "copytree", "move", "mkdir", "makedirs", "touch"}
OS_SHELL = {"system", "popen", "spawnl", "spawnv", "execl", "execv", "execvp", "startfile"}


def _scan_python(name, text):
    out, caps = [], {}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out, caps

    def note(cap, node, why):
        caps.setdefault(cap, (name, getattr(node, "lineno", 0), why))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for mod in mods:
                top = mod.split(".")[0]
                if top in BLOCKED_MODULES:
                    out.append(("block", name, node.lineno, "Importing '%s' is not allowed (it can run arbitrary code or bypass the sandbox rules)." % top))
                if top in NET_MODULES:
                    note("network", node, "imports " + top)
                if top in SUB_MODULES:
                    note("subprocess", node, "imports " + top)
        elif isinstance(node, ast.Call):
            fn = node.func
            fname = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            base = fn.value.id if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) else ""
            if isinstance(fn, ast.Name) and fname in BLOCKED_CALLS:
                out.append(("block", name, node.lineno, "%s() is not allowed: it runs code that cannot be inspected." % fname))
            if base == "os" and fname in OS_SHELL:
                out.append(("block", name, node.lineno, "os.%s() runs shell commands and is not allowed." % fname))
            if base == "subprocess":
                note("subprocess", node, "calls subprocess")
                if any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                    out.append(("block", name, node.lineno, "subprocess with shell=True is not allowed."))
            if fname in FILE_CALLS and (base in ("os", "shutil", "") or isinstance(fn, ast.Attribute)):
                note("files", node, "calls " + fname)
            if fname == "open" and isinstance(fn, ast.Name):
                mode = ""
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    mode = str(node.args[1].value)
                for k in node.keywords:
                    if k.arg == "mode" and isinstance(k.value, ast.Constant):
                        mode = str(k.value.value)
                if any(c in mode for c in "wax+"):
                    note("files", node, "opens a file for writing")
            if base == "os" and fname in ("getenv", "putenv"):
                note("env", node, "reads the environment")
        elif isinstance(node, ast.Attribute) and node.attr == "environ" and isinstance(node.value, ast.Name) and node.value.id == "os":
            note("env", node, "reads the environment")
    return out, caps


JS_BLOCK = (("eval(", re.compile(r"\beval\s*\(")), ("new Function(", re.compile(r"\bnew\s+Function\s*\(")), ("document.write(", re.compile(r"\bdocument\.write\s*\(")), ("javascript: URL", re.compile(r"javascript\s*:", re.I)))
JS_CAPS = (("network", re.compile(r"\b(?:fetch\s*\(|XMLHttpRequest|WebSocket|navigator\.sendBeacon|https?://)")), ("subprocess", re.compile(r"\bchild_process\b")),
           ("files", re.compile(r"\brequire\s*\(\s*['\"]fs['\"]\s*\)|\bfrom\s+['\"]fs['\"]|\bfs\.(?:write|unlink|rm|mkdir|rename)")), ("env", re.compile(r"\bprocess\.env\b")))


def _scan_web(name, text):
    out, caps = [], {}
    for label, rx in JS_BLOCK:
        m = rx.search(text)
        if m:
            out.append(("block", name, text.count("\n", 0, m.start()) + 1, "%s is not allowed." % label))
    for cap, rx in JS_CAPS:
        m = rx.search(text)
        if m and not (cap == "network" and name.endswith((".md", ".json", ".txt"))):
            caps.setdefault(cap, (name, text.count("\n", 0, m.start()) + 1, "uses " + cap))
    if re.search(r"<script[^>]+src\s*=\s*[\"']?https?://", text, re.I):
        out.append(("warn", name, 0, "Loads a script from another site; a reviewer will check it."))
    return out, caps


def stage_security(files, manifest):
    f, caps = [], {}
    for name, body in sorted(files.items()):
        low = name.lower()
        if low.endswith(".py"):
            o, c = _scan_python(name, body.decode("utf-8", "replace"))
        elif low.endswith((".js", ".mjs", ".html", ".svg")):
            o, c = _scan_web(name, body.decode("utf-8", "replace"))
        elif low.endswith((".sh", ".ps1", ".bat")):
            o, c = [("warn", name, 0, "A shell script: a reviewer must read it, and it counts as running commands.")], {"subprocess": (name, 0, "ships a shell script")}
        else:
            continue
        f.extend(o)
        for k, v in c.items():
            caps.setdefault(k, v)
    declared = set((manifest or {}).get("permissions", []))
    for cap, (name, line, why) in sorted(caps.items()):
        if cap not in declared:
            f.append(("block", name, line, "The code %s, but the manifest does not declare the '%s' permission. Declare it in marketplace.json if it is intended." % (why, cap)))
    for cap in sorted(declared - set(caps)):
        f.append(("warn", "marketplace.json", 0, "Declares the '%s' permission but the static scan found no use of it." % cap))
    f.append(("info", "", 0, "Static analysis reads the code only. It cannot prove safety; a reviewer and an isolated test run are still required."))
    return f


# ---------------------------------------------------------------- stage 4: honest listing
def stage_listing(files, manifest, listing, tier="commercial"):
    f = []
    readme = next((b for n, b in files.items() if os.path.basename(n).lower() in ("readme.md", "readme.txt", "readme")), None)
    if readme is None or len(readme.decode("utf-8", "replace").strip()) < 200:
        f.append(("block", "README", 0, "A README of at least 200 characters is required: what it does, how to install and use it, and its limits."))
    lic = (manifest or {}).get("license")
    if tier == "free":
        if lic not in FOSS_LICENSES:
            f.append(("block", "marketplace.json", 0, "The Free and Open tier takes open-source licences only. license must be one of: " + ", ".join(FOSS_LICENSES) + "."))
        lic_file = next((b for n, b in files.items() if os.path.basename(n).upper().split(".")[0] in ("LICENSE", "LICENCE", "COPYING", "UNLICENSE")), None)
        if lic_file is None or len(lic_file.decode("utf-8", "replace").strip()) < 50:
            f.append(("block", "LICENSE", 0, "Include the full licence text in a LICENSE file so people know what they may do with the code."))
    elif lic not in LICENSES:
        f.append(("block", "marketplace.json", 0, "license must be one of: " + ", ".join(LICENSES) + "."))
    for label, text in (("listing title", listing.get("title", "")), ("listing summary", listing.get("summary", "")), ("manifest description", (manifest or {}).get("description", ""))):
        if EARNINGS_CLAIMS.search(str(text)):
            f.append(("block", label, 0, "Income or safety guarantees are not allowed in a listing (for example 'guaranteed', 'passive income', 'make $100')."))
    if EARNINGS_CLAIMS.search(readme.decode("utf-8", "replace") if readme else ""):
        f.append(("warn", "README", 0, "The README contains wording that sounds like an income or safety guarantee; a reviewer will check it."))
    if manifest and str(manifest.get("name", "")).strip().lower() != str(listing.get("title", "")).strip().lower() and listing.get("title"):
        f.append(("info", "", 0, "The listing title differs from the manifest name; the listing title is what buyers see."))
    return f


# ---------------------------------------------------------------- the submission and the pipeline
def _repo_url(u):
    u = str(u or "").strip()
    return u if re.match(r"^https://(?:github\.com|gitlab\.com|codeberg\.org)/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$", u) else ""


def _listing(d, tier="commercial"):
    d = d if isinstance(d, dict) else {}
    cat = d.get("category") if d.get("category") in CATEGORIES else None
    try:
        cents = 0 if tier == "free" else int(round(float(d.get("price", 0)) * 100))
    except (TypeError, ValueError):
        cents = -1
    title = _clean(d.get("title"), 60)
    summary = _clean(d.get("summary"), 240)
    if not title or len(summary) < 20 or not cat or not 0 <= cents <= 100_000_00:
        raise MarketError("A listing needs a title, a summary of at least 20 characters, a category and a price (0 to 100000).")
    out = {"title": title, "summary": summary, "category": cat, "price_cents": cents, "currency": "USD"}
    if tier == "free":
        out["repo_url"] = _repo_url(d.get("repo_url"))
    return out


def _stage_rec(sid, state, findings=None, note="", by="system"):
    return {"id": sid, "state": state, "findings": [{"severity": a, "file": b, "line": c, "text": d} for a, b, c, d in (findings or [])], "note": _clean(note, 300), "by": by, "t": int(time.time())}


def _stage_state(findings):
    return "fail" if any(x[0] == "block" for x in findings) else "pass"


def _ver(sub, n=None):
    v = sub["versions"][-1] if n is None else next((x for x in sub["versions"] if x["n"] == int(n)), None)
    if not v:
        raise MarketError("No such version.")
    return v


def _recompute(sub):
    """Derive the submission status from its stages. Never trusts a stored status."""
    if sub.get("status") in ("withdrawn", "rejected"):
        return
    v = sub["versions"][-1]
    st = v["stages"]
    auto_ok = all(st.get(k, {}).get("state") == "pass" for k in ("intake", "hygiene", "security", "listing"))
    if sub.get("tier") == "free":
        if any(st.get(k, {}).get("state") == "fail" for k in ("intake", "hygiene", "security", "listing", "approval")):
            sub["status"] = "changes_requested"
        elif not auto_ok:
            sub["status"] = "in_review"
        elif not sub.get("declaration") or sub["declaration"].get("sha256") != FREE_DECLARATION_SHA:
            sub["status"] = "awaiting_declaration"
        elif st.get("approval", {}).get("state") != "pass":
            sub["status"] = "awaiting_approval"
        else:
            sub["status"] = "published"
        return
    if any(st.get(k, {}).get("state") == "fail" for k in ("intake", "hygiene", "security", "listing", "functional", "review")):
        sub["status"] = "changes_requested"
    elif not auto_ok:
        sub["status"] = "in_review"
    elif st.get("functional", {}).get("state") != "pass":
        sub["status"] = "awaiting_tests"
    elif st.get("review", {}).get("state") != "pass":
        sub["status"] = "awaiting_review"
    elif not sub.get("agreement") or sub["agreement"].get("version") != AGREEMENT_VERSION:
        sub["status"] = "awaiting_agreement"
    elif st.get("greenlight", {}).get("state") != "pass":
        sub["status"] = "awaiting_greenlight"
    else:
        sub["status"] = "published"


def create_submission(team_id, listing, creator="you", tier="commercial"):
    if tier not in TIERS:
        raise MarketError("A submission is commercial or free.")
    if tier == "free":                                              # anyone can share open-source code; no company is needed
        team = {"id": "free", "name": _clean(creator, 40) or "Community"}
    else:
        team = next((t for t in teams.list_teams() if t["id"] == str(team_id)), None)
        if not team or team["kind"] != "company":
            raise MarketError("Paid products are submitted by a micro-company: create a company workspace first.")
    lst = _listing(listing, tier)
    with _LOCK:
        subs = _read()
        sub = {"id": uuid.uuid4().hex[:10], "tier": tier, "team_id": team["id"], "team_name": team["name"], "creator": _clean(creator, 40), "created": int(time.time()), "listing": lst, "versions": [],
               "agreement": None, "declaration": None, "status": "draft", "published": None, "discount": None}
        subs.append(sub)
        _write(subs)
    _audit(sub["id"], creator, "created", lst["title"])
    return sub


def upload_version(sid, data, filename=""):
    """Store the bundle inertly and run the four automatic stages. The bundle is only ever READ."""
    files = read_bundle(data)
    intake, manifest = stage_intake(files)
    stages = {"intake": _stage_rec("intake", _stage_state(intake), intake)}
    hyg = stage_hygiene(files)
    stages["hygiene"] = _stage_rec("hygiene", _stage_state(hyg), hyg)
    if manifest is None or any(x[0] == "block" for x in intake):
        stages["security"] = _stage_rec("security", "locked", note="Fix the intake problems first.")
        stages["listing"] = _stage_rec("listing", "locked", note="Fix the intake problems first.")
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        if sub.get("status") in ("withdrawn", "rejected"):
            raise MarketError("This submission is closed.")
        if "security" not in stages:
            sec = stage_security(files, manifest)
            stages["security"] = _stage_rec("security", _stage_state(sec), sec)
            lst = stage_listing(files, manifest, sub["listing"], sub.get("tier", "commercial"))
            stages["listing"] = _stage_rec("listing", _stage_state(lst), lst)
        sha = hashlib.sha256(data).hexdigest()
        readme_raw = next((b for nm, b in files.items() if os.path.basename(nm).lower() in ("readme.md", "readme.txt", "readme")), b"")
        readme = readme_raw.decode("utf-8", "replace")[:6000]
        seo_rec = seo.generate(sub["listing"], manifest, readme, sorted(files), sub.get("tier", "commercial"), sub["id"], sub["listing"].get("repo_url", "")) if manifest else None
        n = len(sub["versions"]) + 1
        os.makedirs(BLOB_DIR, exist_ok=True)
        with open(os.path.join(BLOB_DIR, "%s-v%d.zip" % (sub["id"], n)), "wb") as f:           # stored as an inert blob: never extracted, imported or run by NEXXUS
            f.write(data)
        for k, title, kind in (FREE_STAGES if sub.get("tier") == "free" else STAGES)[4:]:
            stages[k] = _stage_rec(k, "waiting", note="")
        sub["versions"].append({"n": n, "t": int(time.time()), "filename": _clean(os.path.basename(filename), 80), "sha256": sha, "bytes": len(data), "files": len(files),
                                "manifest": {k: manifest.get(k) for k in ("name", "version", "kind", "license", "permissions", "description")} if manifest else None, "stages": stages,
                                "readme": readme, "seo": seo_rec})
        _recompute(sub)
        _write(subs)
    _audit(sid, sub["creator"], "uploaded", "v%d %s" % (n, sha[:12]))
    return sub


def attest_tests(sid, reviewer, report, environment, passed, failed):
    """ADMIN. Record that a person ran the functional and stress tests in an isolated environment. A thin report is refused."""
    report, environment = _clean(report, 4000), _clean(environment, 200)
    try:
        passed, failed = int(passed), int(failed)
    except (TypeError, ValueError):
        raise MarketError("passed and failed must be numbers.")
    if len(report) < 100 or len(environment) < 5 or passed < 1 or not _clean(reviewer, 40):
        raise MarketError("Attest with your name, the isolated environment you used, at least one passing test and a report of at least 100 characters (what you ran, with bad inputs and repeated runs).")
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        _need_tier(sub, "commercial")
        v = _ver(sub)
        if any(v["stages"].get(k, {}).get("state") != "pass" for k in ("intake", "hygiene", "security", "listing")):
            raise MarketError("The automatic stages must pass before tests are attested.")
        ok = failed == 0
        v["stages"]["functional"] = _stage_rec("functional", "pass" if ok else "fail", note="%d passed, %d failed in: %s. %s" % (passed, failed, environment, report[:200]), by=_clean(reviewer, 40))
        _recompute(sub)
        _write(subs)
    _audit(sid, reviewer, "tests attested", "%d passed, %d failed" % (passed, failed))
    return sub


def review_signoff(sid, reviewer, checklist, notes, approve):
    """ADMIN. Every checklist item must be ticked to approve."""
    reviewer = _clean(reviewer, 40)
    if not reviewer:
        raise MarketError("Sign the review with your name.")
    checklist = checklist if isinstance(checklist, dict) else {}
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        _need_tier(sub, "commercial")
        v = _ver(sub)
        if v["stages"].get("functional", {}).get("state") != "pass":
            raise MarketError("The functional and stress tests must be attested and pass first.")
        if approve and not all(checklist.get(k) is True for k in REVIEW_CHECKLIST):
            raise MarketError("To approve, every item on the checklist must be ticked: " + ", ".join(k for k in REVIEW_CHECKLIST if checklist.get(k) is not True) + ".")
        v["stages"]["review"] = _stage_rec("review", "pass" if approve else "fail", note=_clean(notes, 300) or ("Approved." if approve else "Changes requested."), by=reviewer)
        _recompute(sub)
        _write(subs)
    _audit(sid, reviewer, "review " + ("approved" if approve else "declined"), _clean(notes, 100))
    return sub


def sign_agreement(sid, legal_name, acks):
    """CREATOR. Only after stages 1-6 pass. Records who signed, when, and the exact text (by hash) they agreed to."""
    name = _clean(legal_name, 80)
    acks = acks if isinstance(acks, dict) else {}
    if len(name) < 3 or " " not in name:
        raise MarketError("Type your full legal name to sign.")
    if not all(acks.get(k) is True for k in AGREEMENT_ACKS):
        raise MarketError("Tick every acknowledgement to sign: " + ", ".join(AGREEMENT_ACKS) + ".")
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        _need_tier(sub, "commercial")
        v = _ver(sub)
        if any(v["stages"].get(k, {}).get("state") != "pass" for k in ("intake", "hygiene", "security", "listing", "functional", "review")):
            raise MarketError("The agreement can be signed only after the testing gauntlet is passed.")
        sub["agreement"] = {"name": name, "t": int(time.time()), "version": AGREEMENT_VERSION, "sha256": AGREEMENT_SHA, "revenue_share_percent": REVENUE_SHARE_PERCENT}
        _recompute(sub)
        _write(subs)
    _audit(sid, name, "agreement signed", "%s %d%% share" % (AGREEMENT_VERSION, REVENUE_SHARE_PERCENT))
    return sub


def _need_tier(sub, tier):
    if sub.get("tier", "commercial") != tier:
        raise MarketError("That step belongs to the %s tier." % ("paid" if tier == "commercial" else "Free and Open"))


def _publish_free(sub, v, who):
    v["stages"]["approval"] = _stage_rec("approval", "pass", note="Published.", by=_clean(who, 40) or "system")
    sub["published"] = {"t": int(time.time()), "version": v["n"], "checkout_url": "", "listing": dict(sub["listing"]), "manifest": v["manifest"], "sha256": v["sha256"], "seo": v.get("seo"), "readme": v.get("readme", "")}
    _recompute(sub)


def sign_declaration(sid, legal_name, acks):
    """CREATOR, Free and Open tier. Replaces the paid tier's agreement: no payments, no revenue share, just a plain statement that the code is theirs to share and safe to run."""
    name = _clean(legal_name, 80)
    acks = acks if isinstance(acks, dict) else {}
    if len(name) < 3:
        raise MarketError("Type your name to sign.")
    if not all(acks.get(k) is True for k in FREE_ACKS):
        raise MarketError("Tick every acknowledgement to sign: " + ", ".join(FREE_ACKS) + ".")
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        _need_tier(sub, "free")
        v = _ver(sub)
        if any(v["stages"].get(k, {}).get("state") != "pass" for k in ("intake", "hygiene", "security", "listing")):
            raise MarketError("The automatic safety checks must pass before you sign.")
        sub["declaration"] = {"name": name, "t": int(time.time()), "sha256": FREE_DECLARATION_SHA}
        if os.environ.get("NEXXUS_FREE_AUTOPUBLISH") == "1":           # off by default: unreviewed code from strangers should meet a person first
            _publish_free(sub, v, "auto-publish (administrator enabled)")
        else:
            _recompute(sub)
        _write(subs)
    _audit(sid, name, "declaration signed", "free tier")
    return sub


def approve_free(sid, admin_name, note=""):
    """ADMIN, Free and Open tier: after reading the automatic report, approve it for the Free and Open section."""
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        _need_tier(sub, "free")
        v = _ver(sub)
        if any(v["stages"].get(k, {}).get("state") != "pass" for k in ("intake", "hygiene", "security", "listing")) or not sub.get("declaration"):
            raise MarketError("The automatic checks must pass and the creator must sign the declaration first.")
        _publish_free(sub, v, admin_name)
        _write(subs)
    _audit(sid, admin_name, "free product approved", _clean(note, 100))
    return sub


def _https(u):
    u = str(u or "").strip()
    return u if re.match(r"^https://[^\s<>\"']{4,400}$", u) else ""


def _discount(d):
    if not d:
        return None
    try:
        pct = int(d.get("percent"))
    except (AttributeError, TypeError, ValueError):
        raise MarketError("A discount needs a percent from 1 to 90.")
    until = str(d.get("until", ""))
    if not 1 <= pct <= 90 or (until and not re.match(r"^\d{4}-\d{2}-\d{2}$", until)):
        raise MarketError("A discount is 1 to 90 percent, with an optional end date (YYYY-MM-DD).")
    return {"percent": pct, "until": until, "label": _clean(d.get("label"), 40) or "Sale"}


def greenlight(sid, admin_name, checkout_url="", discount=None):
    """ADMIN. Publishes the product. The checkout link may be added now or later; without one the Buy button stays off."""
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        _need_tier(sub, "commercial")
        v = _ver(sub)
        if any(v["stages"].get(k, {}).get("state") != "pass" for k in ("intake", "hygiene", "security", "listing", "functional", "review")):
            raise MarketError("The testing gauntlet is not passed.")
        if not sub.get("agreement") or sub["agreement"].get("version") != AGREEMENT_VERSION:
            raise MarketError("The partnership agreement must be signed first.")
        if checkout_url and not _https(checkout_url):
            raise MarketError("The checkout link must be an https address.")
        v["stages"]["greenlight"] = _stage_rec("greenlight", "pass", note="Published.", by=_clean(admin_name, 40) or "admin")
        sub["published"] = {"t": int(time.time()), "version": v["n"], "checkout_url": _https(checkout_url), "listing": dict(sub["listing"]), "manifest": v["manifest"], "sha256": v["sha256"], "seo": v.get("seo"), "readme": v.get("readme", "")}
        sub["discount"] = _discount(discount)
        _recompute(sub)
        _write(subs)
    _audit(sid, admin_name, "published", "v%d" % v["n"])
    return sub


def set_checkout(sid, admin_name, checkout_url, discount=None):
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        if not sub.get("published"):
            raise MarketError("Only a published product has a checkout link.")
        if checkout_url and not _https(checkout_url):
            raise MarketError("The checkout link must be an https address.")
        sub["published"]["checkout_url"] = _https(checkout_url)
        sub["discount"] = _discount(discount)
        _write(subs)
    _audit(sid, admin_name, "checkout/discount set", "")
    return sub


def reject(sid, admin_name, reason):
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        sub["status"] = "rejected"
        sub["rejected"] = {"t": int(time.time()), "reason": _clean(reason, 300)}
        sub["published"] = None
        _write(subs)
    _audit(sid, admin_name, "rejected", _clean(reason, 100))
    return sub


def unpublish(sid, admin_name, reason):
    """Takedown: the product leaves the storefront at once. Buyers keep what they bought."""
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        if not sub.get("published"):
            raise MarketError("That product is not published.")
        sub["published"] = None
        sub["status"] = "rejected"
        sub["rejected"] = {"t": int(time.time()), "reason": "Taken down: " + _clean(reason, 280)}
        _write(subs)
    _audit(sid, admin_name, "taken down", _clean(reason, 100))
    return sub


def withdraw(sid, creator):
    with _LOCK:
        subs = _read()
        sub = _find(subs, sid)
        sub["status"] = "withdrawn"
        sub["published"] = None
        _write(subs)
    _audit(sid, creator, "withdrawn", "")
    return sub


def report_listing(sid, reason, reporter="visitor"):
    """Anyone can report a listing; the administrator sees the reports and can take a product down."""
    reason = _clean(reason, 500)
    if len(reason) < 10:
        raise MarketError("Say what is wrong in at least a sentence.")
    with _LOCK:
        sub = _find(_read(), sid)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(REPORTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time()), "id": sub["id"], "title": sub["listing"]["title"], "reason": reason, "by": _clean(reporter, 40)}) + "\n")
    _audit(sid, reporter, "reported", reason[:100])


def reports(limit=100):
    out = []
    try:
        with open(REPORTS_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return list(reversed(out))[:limit]


# ---------------------------------------------------------------- views
def pipeline_view(sub):
    """The creator's and reviewer's full view of where a submission is, stage by stage."""
    v = sub["versions"][-1] if sub["versions"] else None
    stages = []
    prior_ok = True
    for sid_, title, kind in (FREE_STAGES if sub.get("tier") == "free" else STAGES):
        rec = (v or {}).get("stages", {}).get(sid_)
        if sid_ == "declaration":
            ok = bool(sub.get("declaration") and sub["declaration"].get("sha256") == FREE_DECLARATION_SHA)
            rec = {"id": "declaration", "state": "pass" if ok else ("waiting" if prior_ok else "locked"), "findings": [], "note": ("Signed by %s" % sub["declaration"]["name"]) if ok else "", "by": ""}
        if sid_ == "agreement":
            ok = bool(sub.get("agreement") and sub["agreement"].get("version") == AGREEMENT_VERSION)
            rec = {"id": "agreement", "state": "pass" if ok else ("waiting" if prior_ok else "locked"), "findings": [], "note": ("Signed by %s" % sub["agreement"]["name"]) if ok else "", "by": ""}
        state = (rec or {}).get("state") or ("waiting" if prior_ok and v else "locked")
        if state == "waiting" and not prior_ok:
            state = "locked"                                   # an earlier stage has not passed, so this one cannot start
        stages.append({"id": sid_, "title": title, "kind": kind, "state": state, "findings": (rec or {}).get("findings", []), "note": (rec or {}).get("note", ""), "by": (rec or {}).get("by", ""), "t": (rec or {}).get("t")})
        prior_ok = prior_ok and state == "pass"
    return stages


def creator_view(sub):
    v = sub["versions"][-1] if sub["versions"] else None
    return {"id": sub["id"], "tier": sub.get("tier", "commercial"), "team_id": sub["team_id"], "team_name": sub["team_name"], "listing": sub["listing"], "status": sub["status"], "created": sub["created"], "stages": pipeline_view(sub),
            "version": {k: v[k] for k in ("n", "t", "filename", "sha256", "bytes", "files", "manifest")} if v else None, "versions": len(sub["versions"]),
            "agreement": sub.get("agreement"), "published": bool(sub.get("published")), "rejected": sub.get("rejected"), "discount": sub.get("discount"),
            "agreement_text": AGREEMENT_TEXT, "agreement_version": AGREEMENT_VERSION, "revenue_share_percent": REVENUE_SHARE_PERCENT, "review_checklist": list(REVIEW_CHECKLIST),
            "declaration": sub.get("declaration"), "declaration_text": FREE_DECLARATION, "free_acks": list(FREE_ACKS)}


def list_submissions(team_ids=None):
    return [creator_view(s) for s in _read() if team_ids is None or s["team_id"] in team_ids]


def get_submission(sid):
    return creator_view(_find(_read(), sid))


def _price(listing, discount, today=None):
    cents = listing["price_cents"]
    today = today or time.strftime("%Y-%m-%d")
    live = bool(discount and (not discount.get("until") or discount["until"] >= today) and cents > 0)
    now = int(round(cents * (100 - discount["percent"]) / 100)) if live else cents
    return {"price_cents": cents, "final_cents": now, "discount": discount if live else None}


def _vet_summary(sub):
    v = next((x for x in sub["versions"] if x["n"] == sub["published"]["version"]), None)
    st = (v or {}).get("stages", {})
    return {"automatic": [k for k in ("intake", "hygiene", "security", "listing") if st.get(k, {}).get("state") == "pass"], "tests_attested_by_person": st.get("functional", {}).get("state") == "pass",
            "human_reviewed": st.get("review", {}).get("state") == "pass" or st.get("approval", {}).get("state") == "pass", "agreement_signed": bool(sub.get("agreement") or sub.get("declaration")), "version": sub["published"]["version"],
            "permissions": (sub["published"].get("manifest") or {}).get("permissions", []), "published": sub["published"]["t"]}


def _public_card(sub, today=None):
    pub = sub["published"]
    free = sub.get("tier") == "free"
    card = {"id": sub["id"], "tier": sub.get("tier", "commercial"), "free": free,
            "title": pub["listing"]["title"], "summary": pub["listing"]["summary"], "category": pub["listing"]["category"], "seller": sub["team_name"],
            "version": (pub.get("manifest") or {}).get("version"), "license": (pub.get("manifest") or {}).get("license"), "kind": (pub.get("manifest") or {}).get("kind"),
            "buy_url": pub.get("checkout_url") or "", "currency": pub["listing"]["currency"], "vetting": _vet_summary(sub)}
    card.update(_price(pub["listing"], sub.get("discount"), today))
    rating = social.summary(sub["id"])
    card.update({"slug": (pub.get("seo") or {}).get("slug", ""), "rating": {"avg": rating["avg"], "count": rating["count"]}, "comments": social.count_comments(sub["id"])})
    if free:                                                # only the Free and Open tier publishes its repository link and checksum (anyone may inspect and verify that code)
        card["repo_url"] = pub["listing"].get("repo_url", "")
        card["sha256"] = pub["sha256"]
    return card


def public_catalog(q="", category="", sort="new", today=None, tier="all"):
    """What a buyer sees: published, vetted products only. Nothing else about a submission is ever included. tier: all, commercial or free."""
    q = str(q or "").strip().lower()[:60]
    out = [_public_card(s, today) for s in _read() if s.get("published") and s.get("status") not in ("rejected", "withdrawn")]
    if tier in TIERS:
        out = [c for c in out if c["tier"] == tier]
    if category in CATEGORIES:
        out = [c for c in out if c["category"] == category]
    if q:
        out = [c for c in out if q in (c["title"] + " " + c["summary"] + " " + c["seller"]).lower()]
    key = {"price_low": lambda c: c["final_cents"], "price_high": lambda c: -c["final_cents"], "name": lambda c: c["title"].lower()}.get(sort, lambda c: -next(s for s in _read() if s["id"] == c["id"])["published"]["t"])
    out.sort(key=key)
    return {"products": out, "categories": list(CATEGORIES), "on_sale": sum(1 for c in out if c["discount"]), "total": len(out), "tier": tier if tier in TIERS else "all",
            "counts": {"commercial": sum(1 for c in out if c["tier"] == "commercial"), "free": sum(1 for c in out if c["tier"] == "free")}}


def _bundle_bytes(sub, version):
    """The stored zip for a version, verified against its recorded hash."""
    v = next((x for x in sub["versions"] if x["n"] == int(version)), None)
    if not v:
        raise MarketError("No such version.")
    try:
        with open(os.path.join(BLOB_DIR, "%s-v%d.zip" % (sub["id"], v["n"])), "rb") as f:
            data = f.read()
    except OSError:
        raise MarketError("The stored bundle is missing.")
    if hashlib.sha256(data).hexdigest() != v["sha256"]:
        raise MarketError("The stored bundle no longer matches its recorded checksum, so it is not served.")
    return data, v


def _free_published(sid):
    sub = _find(_read(), sid)
    if sub.get("tier") != "free" or not sub.get("published") or sub.get("status") in ("rejected", "withdrawn"):
        raise MarketError("No such free product.")
    return sub


def free_files(sid):
    """File names and sizes of a published Free and Open package, for transparent inspection."""
    sub = _free_published(sid)
    data, v = _bundle_bytes(sub, sub["published"]["version"])
    files = read_bundle(data)
    return {"files": [{"name": n, "bytes": len(b), "text": _is_text(n)} for n, b in sorted(files.items())], "sha256": v["sha256"], "version": v["n"], "bytes": v["bytes"]}


def free_read(sid, name):
    sub = _free_published(sid)
    data, v = _bundle_bytes(sub, sub["published"]["version"])
    files = read_bundle(data)
    if name not in files:
        raise MarketError("No such file in the package.")
    body = files[name]
    if not _is_text(name):
        return {"name": name, "text": None, "bytes": len(body), "note": "This file is not text, so it is not shown. Download the package to open it."}
    return {"name": name, "text": body[:MAX_VIEW].decode("utf-8", "replace"), "bytes": len(body), "truncated": len(body) > MAX_VIEW}


def free_download(sid):
    """-> (bytes, filename, sha256) of the exact vetted bundle. Only for a published Free and Open package."""
    sub = _free_published(sid)
    data, v = _bundle_bytes(sub, sub["published"]["version"])
    return data, re.sub(r"[^A-Za-z0-9._-]+", "-", sub["listing"]["title"]).strip("-")[:40] + "-" + str((sub["published"].get("manifest") or {}).get("version", "x")) + ".zip", v["sha256"]


def product_page(sid, base_url="", today=None):
    """Everything the product's own page shows: the card, the README as the rich description, the SEO record and structured data (rating included only if real)."""
    sub = _find(_read(), sid)
    if not sub.get("published") or sub.get("status") in ("rejected", "withdrawn"):
        raise MarketError("No such product.")
    card = _public_card(sub, today)
    pub = sub["published"]
    rec = pub.get("seo") or {}
    return {"product": card, "readme": pub.get("readme", ""), "seo": rec, "json_ld": seo.json_ld(card, rec, social.summary(sub["id"]), base_url) if rec else "",
            "path": rec.get("path", ""), "owner": sub["creator"], "tier": sub.get("tier", "commercial")}


def owner_of(sid):
    return _find(_read(), sid)["creator"]


def tier_of(sid):
    return _find(_read(), sid).get("tier", "commercial")


def public_product(sid, today=None):
    sub = _find(_read(), sid)
    if not sub.get("published") or sub.get("status") in ("rejected", "withdrawn"):
        raise MarketError("No such product.")
    return _public_card(sub, today)
