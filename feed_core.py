"""feed_core.py - the signed one-way "source feed": the original NEXXUS publishes real results, every copy pulls them and checks the signature. Nothing flows back and nothing connects into the original.

Used by feed_publish.py (the original: builds and signs) and feed_client.py (a copy: fetches and verifies). It also signs and checks license tokens, with a separate signing domain so a license
signature can never be passed off as a feed, or the other way round.

  signature = Ed25519 over  b"<domain>\\n" + canonical JSON   (domain "nexxus-feed/1" or "nexxus-license/1")
  The private key lives only on the owner's machine (.local_config/, git-ignored). The public key ships with the app (feed_public_key.pem).

A copy refuses a bundle when: the signature does not verify, it is larger than MAX_BYTES, its schema is unknown, its sequence is not newer than the one it already holds (replay), or it is from the future.
A bundle past its valid_until is still shown, but flagged stale, never silently trusted as current. Nothing here runs anything it downloads: a bundle is data. Needs `cryptography` (in requirements.txt)."""
import base64
import json
import os
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SCHEMA = "nexxus-feed/1"
DOMAIN_FEED = b"nexxus-feed/1\n"
DOMAIN_LICENSE = b"nexxus-license/1\n"
MAX_BYTES = 256 * 1024
CLOCK_SKEW_S = 300


class FeedError(Exception):
    pass


def canonical(obj):
    """One exact byte form for a JSON value, so signer and verifier hash the same bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


# ---- keys ----
def generate_keypair():
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    pub_pem = priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return priv_pem, pub_pem


def load_private(pem):
    k = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(k, Ed25519PrivateKey):
        raise FeedError("not an Ed25519 private key")
    return k


def load_public(pem):
    k = serialization.load_pem_public_key(pem)
    if not isinstance(k, Ed25519PublicKey):
        raise FeedError("not an Ed25519 public key")
    return k


# ---- sign / verify ----
def sign(payload, private_pem, domain=DOMAIN_FEED):
    sig = load_private(private_pem).sign(domain + canonical(payload))
    return base64.b64encode(sig).decode("ascii")


def verify_signature(payload, sig_b64, public_pem, domain=DOMAIN_FEED):
    try:
        load_public(public_pem).verify(base64.b64decode(sig_b64, validate=True), domain + canonical(payload))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


# ---- bundles ----
def make_bundle(sequence, sections, valid_hours=48, now=None):
    now = int(now if now is not None else time.time())
    return {"schema": SCHEMA, "sequence": int(sequence), "generated_at": now, "valid_until": now + int(valid_hours * 3600), "sections": sections}


def pack(bundle, private_pem):
    """-> the two files a host serves: latest.json (bundle + signature) bytes."""
    doc = {"bundle": bundle, "signature": sign(bundle, private_pem)}
    data = json.dumps(doc, indent=1, sort_keys=True).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise FeedError("bundle is %d bytes, over the %d byte limit" % (len(data), MAX_BYTES))
    return data


def verify_bundle(raw, public_pem, last_sequence=0, now=None):
    """raw bytes of latest.json -> {"bundle", "stale", "age_s"}; raises FeedError with a plain reason when it must be refused."""
    now = int(now if now is not None else time.time())
    if len(raw) > MAX_BYTES:
        raise FeedError("the feed is larger than the %d byte limit, refused" % MAX_BYTES)
    try:
        doc = json.loads(raw.decode("utf-8"))
        bundle, sig = doc["bundle"], doc["signature"]
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise FeedError("the feed is not in the expected format, refused")
    if not isinstance(bundle, dict) or bundle.get("schema") != SCHEMA:
        raise FeedError("unknown feed schema, refused")
    if not verify_signature(bundle, sig, public_pem):
        raise FeedError("the signature does not match the original NEXXUS key, refused")
    seq, gen, until = bundle.get("sequence"), bundle.get("generated_at"), bundle.get("valid_until")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (seq, gen, until)):
        raise FeedError("the feed has invalid numbers, refused")
    if seq <= int(last_sequence):
        raise FeedError("this feed (number %d) is not newer than the one you already have (%d), refused as a replay" % (seq, last_sequence))
    if gen > now + CLOCK_SKEW_S:
        raise FeedError("the feed claims to be from the future, refused")
    return {"bundle": bundle, "stale": now > until, "age_s": max(0, now - gen)}


# ---- what may be published ----
_UNSAFE = [(re.compile(r"[A-Za-z]:[\\/]"), "a file path"), (re.compile(r"(?<![\d.])(127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+)(?![\d.])"), "a private address"),
           (re.compile(r"AIza[0-9A-Za-z_\-]{20,}|AQ\.[A-Za-z0-9_\-]{20,}|\bsk-[A-Za-z0-9]{16,}|\bghp_[A-Za-z0-9]{20,}"), "an API key"), (re.compile(r"\b[A-Fa-f0-9]{40,}\b"), "a long hex token"),
           (re.compile(r"(?i)\b(password|secret|token|api[_ -]?key)\b\s*[:=]"), "a credential assignment"), (re.compile(r"\\\\[A-Za-z0-9_.-]+\\"), "a network path")]


def assert_public_safe(value, path="bundle"):
    """Fail closed: refuse to publish anything that looks like a path, private address, key or credential. Raises FeedError naming the field, never the value."""
    if isinstance(value, dict):
        for k, v in value.items():
            assert_public_safe(k, path + ".<key>")
            assert_public_safe(v, path + "." + str(k))
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            assert_public_safe(v, "%s[%d]" % (path, i))
    elif isinstance(value, str):
        for rx, what in _UNSAFE:
            if rx.search(value):
                raise FeedError("not public-safe: %s contains %s" % (path, what))
    elif value is not None and not isinstance(value, (int, float, bool)):
        raise FeedError("not public-safe: %s has an unsupported type" % path)
    return True


# ---- licenses ----
def issue_license(number, holder, kind, private_pem, now=None):
    """A signed, offline-checkable token. `number` is whatever you put on the download page for that buyer. Nothing is sent anywhere."""
    claims = {"schema": "nexxus-license/1", "number": str(number)[:64], "holder": str(holder)[:120], "kind": str(kind)[:40], "issued_at": int(now if now is not None else time.time())}
    return {"claims": claims, "signature": sign(claims, private_pem, DOMAIN_LICENSE)}


def check_license(token, public_pem):
    """-> the claims when the signature is the owner's, else raises FeedError. Works offline."""
    try:
        claims, sig = token["claims"], token["signature"]
    except (KeyError, TypeError):
        raise FeedError("not a license token")
    if not isinstance(claims, dict) or claims.get("schema") != "nexxus-license/1" or not verify_signature(claims, sig, public_pem, DOMAIN_LICENSE):
        raise FeedError("license signature is not valid")
    return claims
