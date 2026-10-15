"""billing.py - the desktop side of the Platform subscription: start a Stripe Checkout, then pull the signed licence key once Stripe has confirmed payment.

The money path never touches this computer. relay/billing/worker.js (a Cloudflare Worker you deploy) creates the Checkout Session, receives Stripe's signed webhooks and issues licence keys. This module only:

  * keeps a random claim id + claim secret in nexxus_data/state/billing.json (the Worker stores just the secret's SHA-256),
  * asks the Worker for a Checkout link (start_checkout) and for the current entitlement (refresh),
  * hands a returned key to entitlements.activate(), which checks the Ed25519 signature offline.

Nothing here can lock you out of NEXXUS: every failure (no server configured, offline, Stripe down, declined card, expired or abandoned checkout) is returned as a message and leaves the licence already on
this computer untouched. Only Platform areas ask entitlements.is_unlocked(); NEXXUS core never does. While open Beta is on, none of this is needed and nothing is contacted unless you press Buy.

Configure the Worker address with the environment variable NEXXUS_BILLING_URL or the "url" field of billing_config.json (https only). Unset: Buy says billing is not set up and nothing else changes.
"""
import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.request

import entitlements

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "billing_config.json")
STATE_PATH = os.path.join(HERE, "nexxus_data", "state", "billing.json")
TIMEOUT = 10
MAX_BODY = 20000
_lock = threading.Lock()

# What the person is told for each state the server can report (plain words, no jargon)
MESSAGES = {
    "pending": "Waiting for the payment to finish. If you closed the checkout, press Buy again.",
    "active": "Your subscription is active.",
    "past_due": "Your last payment did not go through. Access continues until the end of the period you paid for; update your card from Manage billing.",
    "canceled": "Your subscription has ended. NEXXUS itself is unaffected; Platform areas stay locked until you subscribe again.",
    "expired": "That checkout expired and you were not charged. Press Buy to start a new one.",
    "failed": "The payment did not go through and you were not charged. Try another card from Buy.",
    "revoked": "This purchase was refunded or disputed, so the key was withdrawn.",
}


def base_url():
    url = os.environ.get("NEXXUS_BILLING_URL", "").strip()
    if not url:
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                url = str(json.load(f).get("url", "")).strip()
        except (OSError, ValueError, AttributeError):
            url = ""
    return url.rstrip("/") if url.startswith("https://") and len(url) < 300 else ""


def configured():
    return bool(base_url())


def _load():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE_PATH), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, STATE_PATH)


def _identity():
    """The claim id and secret, created on first use. They are capabilities for this one computer, not account credentials."""
    d = _load()
    if not (isinstance(d.get("claim"), str) and isinstance(d.get("secret"), str)):
        d = {"claim": secrets.token_hex(12), "secret": secrets.token_hex(24)}
        _save(d)
    return d


def _http(method, url, headers=None, body=None):
    """-> (status, parsed JSON dict). Network trouble raises OSError (callers turn it into a message)."""
    data = json.dumps(body).encode() if body is not None else None
    h = {"Accept": "application/json", "User-Agent": "NEXXUS-billing"}
    if data is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            status, raw = r.status, r.read(MAX_BODY)
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(MAX_BODY)
    try:
        out = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        out = {}
    return status, out if isinstance(out, dict) else {}


_transport = _http          # tests replace this with a fake server


def _unavailable(why="Billing is not set up on this copy of NEXXUS yet."):
    return {"ok": False, "message": why, "configured": configured()}


def start_checkout(plan):
    """-> {"ok": True, "url": https checkout page} or {"ok": False, "message": ...}. Never raises."""
    if plan not in entitlements.PLANS:
        return {"ok": False, "message": "Choose the monthly subscription or the lifetime pass."}
    root = base_url()
    if not root:
        return _unavailable()
    with _lock:
        ident = _identity()
        try:
            status, out = _transport("POST", root + "/checkout", None, {"plan": plan, "claim": ident["claim"], "claim_hash": hashlib.sha256(ident["secret"].encode()).hexdigest()})
        except (OSError, ValueError):
            return {"ok": False, "message": "Could not reach the billing server. Check your connection and try again; nothing was charged and NEXXUS works as before."}
    url = out.get("url")
    if status == 200 and isinstance(url, str) and url.startswith("https://checkout.stripe.com/") and len(url) < 2000:
        return {"ok": True, "url": url}
    if status == 409 and "already active" in str(out.get("error", "")):
        return {"ok": False, "message": "You already have this plan. Press Check my subscription to load your key."}
    if status == 429:
        return {"ok": False, "message": "Too many attempts. Wait a minute and try again."}
    if status == 503:
        return {"ok": False, "message": "Billing is still being set up on the server. Nothing was charged."}
    return {"ok": False, "message": "Could not start checkout. Nothing was charged. Try again in a moment."}


def refresh():
    """Ask the billing server what this computer has paid for and, if it has a key, activate it. A failure of any kind keeps whatever licence is already here. Never raises."""
    root = base_url()
    if not root:
        return {**_unavailable(), "entitlement": entitlements.status()}
    ident = _load()
    if not ident.get("claim"):
        return {"ok": True, "state": "none", "message": "No purchase has been started on this computer.", "entitlement": entitlements.status()}
    try:
        status, out = _transport("GET", root + "/claim?claim=" + ident["claim"], {"X-Claim-Secret": ident["secret"]}, None)
    except (OSError, ValueError):
        return {"ok": False, "message": "Could not reach the billing server just now. Your current access is unchanged.", "entitlement": entitlements.status()}
    if status == 404:
        return {"ok": True, "state": "none", "message": "No payment has been recorded for this computer yet.", "entitlement": entitlements.status()}
    if status != 200:
        return {"ok": False, "message": "The billing server could not answer just now. Your current access is unchanged.", "entitlement": entitlements.status()}
    state = str(out.get("state", ""))[:20]
    token = out.get("token")
    if isinstance(token, str):
        ok, st = entitlements.activate(token)
        if not ok:
            return {"ok": False, "state": state, "message": "The server sent a key this version could not verify: " + st["reason"], "entitlement": entitlements.status()}
    return {"ok": True, "state": state, "plan": out.get("plan"), "cancel_at_period_end": bool(out.get("cancel_at_period_end")),
            "message": MESSAGES.get(state, "Status: " + state), "entitlement": entitlements.status()}


def portal():
    """-> {"ok": True, "url": Stripe customer portal} to update a card or cancel."""
    root, ident = base_url(), _load()
    if not root:
        return _unavailable()
    if not ident.get("claim"):
        return {"ok": False, "message": "There is no subscription on this computer to manage."}
    try:
        status, out = _transport("POST", root + "/portal", None, {"claim": ident["claim"], "secret": ident["secret"]})
    except (OSError, ValueError):
        return {"ok": False, "message": "Could not reach the billing server just now."}
    url = out.get("url")
    if status == 200 and isinstance(url, str) and url.startswith("https://billing.stripe.com/"):
        return {"ok": True, "url": url}
    return {"ok": False, "message": "Could not open billing management. If you paid, press Check my subscription first."}


def summary():
    return {"configured": configured(), "started": bool(_load().get("claim")), "at": int(time.time())}
