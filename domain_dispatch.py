"""domain_dispatch.py - the home screen's courier for the four domain hubs (Sports, Markets, Logistics, Economics).

  1. A standard or general prompt is not touched here: the caller takes the regular NEXXUS route.
  2. A prompt that clearly targets exactly ONE hub is packaged and sent, over an internal HTTP request, to that hub's own local port. NEXXUS does not answer it, does not search the web for it and
     does not use a model to decide: the courier is a deterministic dispatcher (no system prompt exists because no model is involved).
  3. The hub's answer comes back exactly as the hub produced it. The reply text is returned unaltered; the hub's whole JSON is passed through beside it, untouched.
  4. If the hub is not answering, the courier says so. It never falls back to answering the question itself.

Where each hub listens is set by these variables (placeholders: change them here, in the environment, or in nexxus_env.bat):

    NEXXUS_PORT_SPORTS      default 8721        NEXXUS_PORT_MARKETS    default 8722
    NEXXUS_PORT_LOGISTICS   default 8723        NEXXUS_PORT_ECONOMICS  default 8724
    NEXXUS_DOMAIN_HOST      default 127.0.0.1   (loopback only: any other host is refused)
    NEXXUS_DOMAIN_TIMEOUT   default 600         (seconds a hub may take; a cold local model is slow)
    NEXXUS_DOMAIN_DISPATCH  default 1           (0 switches the courier off and everything takes the regular route)

Each hub process is started with  python domain_hub_server.py <domain>  (start_domain_hubs.bat starts all four). A hub process only ever serves its own domain.
"""
import json
import os
import re
import urllib.error
import urllib.request

import portal_chat
import portals

LOOPBACK = ("127.0.0.1", "localhost", "::1")
MAX_REPLY_BYTES = 1_048_576
CONNECT_PROBE_S = 2.0

# ---- placeholders: the local port of each domain hub ----
DOMAIN_PORT_DEFAULTS = {"sports": 8721, "markets": 8722, "logistics": 8723, "economics": 8724}

# prompts that are commands or builds, not questions about the domain, always stay on the regular route ("build me a sports dashboard" is a build request)
_NOT_A_QUESTION = re.compile(r"^\s*(?:(?:build|create|make|generate|design|write|code|fetch|ingest|engine|link|diagnose|approve|reject|install|deploy)\b|(?:search|data)\s*:)|\b(?:build|create|generate)\s+(?:me\s+)?(?:a|an|the)\b", re.I)


def host():
    return os.environ.get("NEXXUS_DOMAIN_HOST", "127.0.0.1").strip()


def port(domain):
    raw = os.environ.get("NEXXUS_PORT_%s" % domain.upper(), "")
    try:
        p = int(raw) if raw else DOMAIN_PORT_DEFAULTS[domain]
    except ValueError:
        p = DOMAIN_PORT_DEFAULTS[domain]
    return p if 1 <= p <= 65535 else DOMAIN_PORT_DEFAULTS[domain]


def enabled():
    return os.environ.get("NEXXUS_DOMAIN_DISPATCH", "1") != "0"


def timeout_s():
    try:
        return max(5.0, float(os.environ.get("NEXXUS_DOMAIN_TIMEOUT", "600")))
    except ValueError:
        return 600.0


def url(domain, path="/chat"):
    h = host()
    if h not in LOOPBACK:
        raise portals.PortalError("the domain hubs are internal: %r is not a loopback address" % h)
    return "http://%s:%d%s" % ("[::1]" if h == "::1" else h, port(domain), path)


def config():
    """What the courier is set to (for the status route and the start script)."""
    return {"enabled": enabled(), "host": host(), "timeout_s": timeout_s(),
            "hubs": {d: {"port": port(d), "url": url(d) if host() in LOOPBACK else None} for d in portals.ORDER}}


def target(message):
    """Which ONE hub does this prompt clearly belong to? -> (domain or None, why). Deterministic. Anything that is not clearly one hub's (no signal, a mix, a tie, a build request) is None."""
    msg = str(message or "").strip()
    if not msg or len(msg) > portal_chat.MAX_MESSAGE:
        return None, "empty or too long"
    if _NOT_A_QUESTION.search(msg):
        return None, "command or build request"
    if portal_chat._INJECTION.search(msg):
        return None, "instruction-like text"
    gates = {d: portal_chat.gate(d, msg) for d in portals.ORDER}
    owners = [d for d, g in gates.items() if g["ok"] and g["reason"] == "in_domain"]
    if len(owners) == 1:
        return owners[0], "clearly %s" % owners[0]
    return None, ("ambiguous between %s" % ", ".join(owners)) if owners else "no single hub owns it"


def send(domain, message):
    """Package the prompt and POST it to that hub's port. -> {ok, hub: <the hub's JSON, untouched>, reply: <its reply, untouched>} or {ok: False, error, ...}. Never raises."""
    try:
        u = url(domain)
    except portals.PortalError as e:
        return {"ok": False, "error": str(e), "domain": domain}
    body = json.dumps({"portal": domain, "message": str(message)}).encode("utf-8")
    req = urllib.request.Request(u, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s()) as r:
            raw = r.read(MAX_REPLY_BYTES + 1)
            status = r.status
    except urllib.error.HTTPError as e:                                            # the hub answered with an error status: its own words are still the answer
        raw, status = e.read(MAX_REPLY_BYTES + 1), e.code
    except (urllib.error.URLError, ConnectionError, OSError, TimeoutError) as e:
        why = getattr(e, "reason", e)
        return {"ok": False, "domain": domain, "port": port(domain), "error": "the %s hub is not answering on port %d (%s)" % (domain.title(), port(domain), type(why).__name__)}
    if len(raw) > MAX_REPLY_BYTES:
        return {"ok": False, "domain": domain, "port": port(domain), "error": "the %s hub's reply was larger than %d bytes and was not forwarded" % (domain.title(), MAX_REPLY_BYTES)}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("reply"), str):
        return {"ok": False, "domain": domain, "port": port(domain), "error": "the %s hub returned something that is not a hub reply (HTTP %s)" % (domain.title(), status)}
    return {"ok": True, "domain": domain, "port": port(domain), "http": status, "hub": payload, "reply": payload["reply"]}


def route(message):
    """The one entry point for the home screen. -> None when the prompt is standard (take the regular route), else the courier's result dict (see send())."""
    if not enabled():
        return None
    domain, _why = target(message)
    if domain is None:
        return None
    return send(domain, message)


def courier_error_text(res):
    """What the home screen shows when a hub could not be reached: the courier reports, it does not answer in the hub's place."""
    return "%s Start the domain hubs with start_domain_hubs.bat (port %s). NEXXUS does not answer %s questions itself." % (
        res["error"][:1].upper() + res["error"][1:] + ".", res.get("port", "?"), res.get("domain", "domain").title())
