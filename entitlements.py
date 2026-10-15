"""entitlements.py - the access gate for Platform mode: is there a valid, signed license on this machine?

NEXXUS never handles payments or card details. Buying goes through Stripe Checkout (billing.py + relay/billing/worker.js), which hands back a license key; keys can also still be issued by hand with
tools/issue_license.py and pasted in. The key is a token signed with the owner's Ed25519 private key; this module checks it OFFLINE against the public key shipped in license_public_key.pem,
on every call (a saved file is never trusted on its own).

    token = "NXP1." + base64url(payload JSON) + "." + base64url(signature)
    payload = {"feature": "platform", "plan": "monthly" | "lifetime", "iat": issued-at, "exp": expiry or null (lifetime), "id": random id}

Honest limits: this is a local gate in source-available software. Someone who edits the code can remove it, and an offline check cannot revoke a key (a monthly key simply stops working at its
expiry, so a subscription is renewed by issuing a new key). Real enforcement belongs on the server side of any networked Platform feature.
"""
import base64
import json
import os
import tempfile
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_KEY_PATH = os.path.join(HERE, "license_public_key.pem")
BETA_PATH = os.path.join(HERE, "platform_beta.json")
LICENSE_PATH = os.path.join(HERE, "nexxus_data", "state", "license.json")
PREFIX = "NXP1"
FEATURE = "platform"
MAX_TOKEN = 2000

PLANS = {
    "monthly": {"label": "Monthly subscription", "price_usd": 9.99, "price_text": "$9.99 / month", "period": "month"},
    "lifetime": {"label": "Lifetime Access Pass", "price_usd": 199.00, "price_text": "$199 one-time", "period": "once"},
}


# Which Platform areas each tier unlocks. "enterprise" is reserved for a future plan: a signed key may carry it, but nothing sells it yet and PLANS has no price for it.
TIERS = {
    "beta": frozenset({"academy", "teams", "marketplace", "floor", "talk"}),
    "platform": frozenset({"academy", "teams", "marketplace", "floor", "talk"}),
    "enterprise": frozenset({"academy", "teams", "marketplace", "floor", "talk"}),
}


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _public_key():
    with open(PUBLIC_KEY_PATH, "rb") as f:
        return serialization.load_pem_public_key(f.read())


def verify(token, now=None):
    """-> {"valid": bool, "reason": str, "plan": str|None, "exp": int|None, "id": str|None}. Never raises."""
    now = time.time() if now is None else now
    bad = lambda why: {"valid": False, "reason": why, "plan": None, "exp": None, "id": None}
    try:
        token = str(token or "").strip()
        if not token or len(token) > MAX_TOKEN:
            return bad("no license key")
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != PREFIX:
            return bad("not a NEXXUS license key")
        payload_b, sig = _b64d(parts[1]), _b64d(parts[2])
        try:
            _public_key().verify(sig, parts[0].encode() + b"." + payload_b)
        except InvalidSignature:
            return bad("the signature does not match (the key was changed or is not genuine)")
        p = json.loads(payload_b)
        if p.get("feature") != FEATURE or p.get("plan") not in PLANS:
            return bad("this key is not for Platform mode")
        if p.get("tier", "platform") not in TIERS or p.get("tier") == "beta":
            return bad("this key is for a tier this version does not know")
        exp = p.get("exp")
        if p["plan"] == "lifetime":
            exp = None
        elif not isinstance(exp, (int, float)) or isinstance(exp, bool):
            return bad("a monthly key needs an expiry")
        if exp is not None and now > exp:
            return {"valid": False, "reason": "this monthly key expired on " + time.strftime("%Y-%m-%d", time.gmtime(exp)), "plan": p["plan"], "exp": int(exp), "id": p.get("id")}
        return {"valid": True, "reason": "ok", "plan": p["plan"], "exp": None if exp is None else int(exp), "id": p.get("id"), "tier": p.get("tier", "platform")}
    except Exception:
        return bad("the key could not be read")


def beta_open():
    """True while Platform is in open Beta: everyone gets in with no license. Controlled by platform_beta.json ({"beta_open": true}); the environment variable NEXXUS_PLATFORM_BETA=0 forces the gate back on
    (used for testing and for the day the beta ends). The license checks below stay in place either way."""
    if os.environ.get("NEXXUS_PLATFORM_BETA", "").strip().lower() in ("0", "false", "off", "no"):
        return False
    try:
        with open(BETA_PATH, encoding="utf-8") as f:
            return bool(json.load(f).get("beta_open", False))
    except (OSError, ValueError, AttributeError):
        return False


def _saved_token():
    try:
        with open(LICENSE_PATH, encoding="utf-8") as f:
            return json.load(f).get("token", "")
    except (OSError, ValueError, AttributeError):
        return ""


def status(now=None):
    if beta_open():
        return {"unlocked": True, "plan": "beta", "expires": None, "beta": True, "reason": "open Beta: Platform is unlocked for everyone"}
    v = verify(_saved_token(), now)
    return {"unlocked": v["valid"], "plan": v["plan"], "expires": v["exp"], "beta": False, "tier": v.get("tier"), "reason": v["reason"] if _saved_token() else "locked: no license key on this computer"}


def is_unlocked():
    return status()["unlocked"]


def activate(token, now=None):
    """Verify and save a key. -> (ok, status dict). A bad key is never saved."""
    v = verify(token, now)
    if not v["valid"]:
        return False, {"unlocked": False, "plan": None, "expires": None, "reason": v["reason"]}
    os.makedirs(os.path.dirname(LICENSE_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(LICENSE_PATH), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"token": str(token).strip()}, f)
    os.replace(tmp, LICENSE_PATH)
    return True, status(now)


def remove():
    try:
        os.remove(LICENSE_PATH)
    except OSError:
        pass
    return status()


def allows(feature, now=None):
    """True when the current entitlement unlocks `feature` (academy / teams / marketplace). Beta and every paid tier in TIERS unlock what the tier lists; a lapsed or missing licence unlocks nothing here, and
    NEXXUS core never asks this question: only Platform's own areas do."""
    st = status(now)
    if not st["unlocked"]:
        return False
    return feature in TIERS.get(st.get("tier") or ("platform" if st["plan"] != "beta" else "beta"), ())


def offer():
    """What the pricing screen shows. Buying goes through billing.py (Stripe Checkout, hosted by Stripe), so no link or card detail lives here."""
    return {"plans": [{"id": k, **v} for k, v in PLANS.items()], "entitlement": status(), "beta": beta_open(), "tiers": {k: sorted(v) for k, v in TIERS.items()}}
