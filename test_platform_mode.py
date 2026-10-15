import base64
import json
import os
import sys
import tempfile
import time
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import Flask, jsonify

import entitlements as ent
import platform_mode as pm

KEY = Ed25519PrivateKey.generate()


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def token(plan="lifetime", exp=None, feature="platform", key=KEY, tamper=False):
    body = json.dumps({"feature": feature, "plan": plan, "iat": int(time.time()), "exp": exp, "id": "t1"}, separators=(",", ":")).encode()
    t = "NXP1." + b64(body) + "." + b64(key.sign(b"NXP1." + body))
    return t[:-3] + ("AAA" if tamper else t[-3:])


class FakeModes:
    DEFAULT_MODE = "conversation"
    MODES = {"conversation": {}}


class FakeState:
    def __init__(self):
        self.mode = "conversation"

    def set(self, m):
        if m not in FakeModes.MODES:
            raise ValueError("unknown mode")
        self.mode = m
        return {"mode": m}

    def snapshot(self):
        return {"mode": self.mode}


class Base(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        pub = os.path.join(d, "pub.pem")
        open(pub, "wb").write(KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        ent.PUBLIC_KEY_PATH, ent.LICENSE_PATH = pub, os.path.join(d, "license.json")
        pm.DATA_DIR = os.path.join(d, "platform")
        pm.PROFILE_PATH, pm.POSTS_PATH = os.path.join(pm.DATA_DIR, "p.json"), os.path.join(pm.DATA_DIR, "posts.jsonl")
        FakeModes.MODES = {"conversation": {}}


class EntitlementTest(Base):
    def test_locked_by_default_and_prices(self):
        self.assertFalse(ent.is_unlocked())
        self.assertEqual(ent.PLANS["monthly"]["price_usd"], 9.99)
        self.assertEqual(ent.PLANS["lifetime"]["price_usd"], 199.00)

    def test_valid_keys_unlock(self):
        self.assertTrue(ent.activate(token("lifetime"))[0])
        ent.remove()
        self.assertTrue(ent.activate(token("monthly", exp=int(time.time()) + 3600))[0])
        self.assertEqual(ent.status()["plan"], "monthly")

    def test_forged_tampered_wrong_feature_expired_are_refused(self):
        other = Ed25519PrivateKey.generate()
        for t, why in ((token(key=other), "signature"), (token(tamper=True), "signature"), (token(feature="other"), "not for Platform"),
                       (token("monthly", exp=int(time.time()) - 5), "expired"), (token("monthly", exp=None), "expiry"), ("garbage", "not a NEXXUS"), ("", "no license")):
            ok, st = ent.activate(t)
            self.assertFalse(ok, t[:20])
            self.assertIn(why, st["reason"])
        self.assertFalse(ent.is_unlocked(), "a refused key is never saved")

    def test_saved_key_is_rechecked_so_expiry_relocks(self):
        ent.activate(token("monthly", exp=int(time.time()) + 100))
        self.assertTrue(ent.status()["unlocked"])
        self.assertFalse(ent.status(now=time.time() + 1000)["unlocked"])

    def test_checkout_links_must_be_https(self):
        os.environ["NEXXUS_CHECKOUT_MONTHLY"], os.environ["NEXXUS_CHECKOUT_LIFETIME"] = "http://insecure.example", "https://buy.example/x"
        try:
            self.assertEqual(ent.checkout_links(), {"monthly": None, "lifetime": "https://buy.example/x"})
        finally:
            del os.environ["NEXXUS_CHECKOUT_MONTHLY"], os.environ["NEXXUS_CHECKOUT_LIFETIME"]


class ModeGateTest(Base):
    def test_locked_until_licensed_and_relocks(self):
        st = FakeState()
        pm.register_mode(st, FakeModes)
        with self.assertRaises(pm.ModeLocked):
            st.set("platform")
        self.assertEqual(st.mode, "conversation")
        ent.activate(token("monthly", exp=int(time.time()) + 100))
        self.assertEqual(st.set("platform")["mode"], "platform")
        ent.remove()
        self.assertEqual(st.snapshot()["mode"], "conversation", "falls back to the desktop view when the license goes")


class RouteTest(Base):
    def setUp(self):
        super().setUp()
        self.local = True
        app = Flask(__name__)
        pm.register_routes(app, lambda: self.local, lambda p, s=200: (jsonify(p), s))
        self.c = app.test_client()

    def test_data_routes_locked_without_license(self):
        for method, url in (("get", "/api/platform/state"), ("post", "/api/platform/post"), ("post", "/api/platform/profile")):
            r = getattr(self.c, method)(url, json={"text": "x"})
            self.assertEqual(r.status_code, 402, url)
            self.assertEqual(r.get_json()["status"], "locked", "the status field must not be overwritten by the entitlement data")
            self.assertEqual(r.get_json()["plans"][1]["price_text"], "$199 one-time")
            self.assertFalse(r.get_json()["entitlement"]["unlocked"])

    def test_entitlement_route_reports_success_and_the_offer(self):
        d = self.c.get("/api/platform/entitlement").get_json()
        self.assertEqual(d["status"], "success")
        self.assertEqual([p["id"] for p in d["plans"]], ["monthly", "lifetime"])
        self.assertFalse(d["entitlement"]["unlocked"])

    def test_license_then_profile_posts_and_links(self):
        self.assertEqual(self.c.post("/api/platform/license", json={"token": "nope"}).status_code, 400)
        self.assertEqual(self.c.post("/api/platform/license", json={"token": token()}).status_code, 200)
        self.c.post("/api/platform/profile", json={"name": "Ada <b>L</b>", "headline": "Builder", "links": ["https://ex.am/p", "javascript:alert(1)", "ftp://x"]})
        p = self.c.post("/api/platform/post", json={"text": "hello floor"}).get_json()["post"]
        q = self.c.post("/api/platform/post", json={"text": "see https://example.com/a?b=1 now"}).get_json()["post"]
        self.assertEqual((p["kind"], q["kind"], q["url"]), ("post", "link", "https://example.com/a?b=1"))
        s = self.c.get("/api/platform/state").get_json()
        self.assertEqual(s["profile"]["links"], ["https://ex.am/p"], "only http(s) links are kept")
        self.assertEqual(len(s["floor"]), 2)
        self.assertEqual(len(s["shared_links"]), 1)
        self.assertEqual(s["network"], {"connections": 0, "feed": [], "note": s["network"]["note"]}, "the network side never shows invented content")
        self.assertEqual(self.c.delete("/api/platform/post/" + p["id"]).status_code, 200)
        self.assertEqual(self.c.delete("/api/platform/post/" + p["id"]).status_code, 404)
        self.assertEqual(self.c.post("/api/platform/post", json={"text": "   "}).status_code, 400)

    def test_not_available_from_other_machines(self):
        self.local = False
        self.assertEqual(self.c.get("/api/platform/entitlement").status_code, 403)
        self.assertEqual(self.c.post("/api/platform/license", json={"token": token()}).status_code, 403)

    def test_text_is_capped_and_cleaned(self):
        self.c.post("/api/platform/license", json={"token": token()})
        p = self.c.post("/api/platform/post", json={"text": "a\x00b" + "x" * 900}).get_json()["post"]
        self.assertEqual(len(p["text"]), 500)
        self.assertNotIn("\x00", p["text"])


if __name__ == "__main__":
    unittest.main()
