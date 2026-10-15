"""tools/issue_license.py - OWNER ONLY. Creates the signing key and issues Platform license keys. Never ship or commit the private key.

    python tools/issue_license.py keygen                 create .local_config/license_private_key.pem and write license_public_key.pem (do this once; BACK UP the private key)
    python tools/issue_license.py issue lifetime         print a Lifetime Access Pass key
    python tools/issue_license.py issue monthly [--days 31]   print a monthly key that stops working after that many days
    python tools/issue_license.py check <key>            verify a key the way the app does

The private key lives in .local_config/ (gitignored). If it is lost, no new keys can be issued: create a new pair and ship the new public key in a release.
"""
import argparse
import base64
import json
import os
import secrets
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import entitlements  # noqa: E402

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

PRIVATE_PATH = os.environ.get("NEXXUS_LICENSE_PRIVATE_KEY") or os.path.join(ROOT, ".local_config", "license_private_key.pem")


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def keygen():
    if os.path.exists(PRIVATE_PATH):
        sys.exit("A private key already exists at %s. Refusing to overwrite it (that would invalidate every key you have issued)." % PRIVATE_PATH)
    os.makedirs(os.path.dirname(PRIVATE_PATH), exist_ok=True)
    key = Ed25519PrivateKey.generate()
    with open(PRIVATE_PATH, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    try:
        os.chmod(PRIVATE_PATH, 0o600)
    except OSError:
        pass
    with open(entitlements.PUBLIC_KEY_PATH, "wb") as f:
        f.write(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    print("Private key written to", PRIVATE_PATH, "(keep it secret and back it up).")
    print("Public key written to", entitlements.PUBLIC_KEY_PATH, "(commit this one).")


def issue(plan, days):
    with open(PRIVATE_PATH, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    now = int(time.time())
    payload = {"feature": entitlements.FEATURE, "plan": plan, "iat": now, "exp": None if plan == "lifetime" else now + days * 86400, "id": secrets.token_hex(6)}
    body = json.dumps(payload, separators=(",", ":")).encode()
    return entitlements.PREFIX + "." + _b64(body) + "." + _b64(key.sign(entitlements.PREFIX.encode() + b"." + body))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keygen")
    i = sub.add_parser("issue"); i.add_argument("plan", choices=list(entitlements.PLANS)); i.add_argument("--days", type=int, default=31)
    c = sub.add_parser("check"); c.add_argument("token")
    a = ap.parse_args()
    if a.cmd == "keygen":
        keygen()
    elif a.cmd == "issue":
        print(issue(a.plan, a.days))
    else:
        print(json.dumps(entitlements.verify(a.token), indent=2))
