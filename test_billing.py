import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import Flask, jsonify

import billing
import entitlements as ent
import platform_mode as pm
from test_platform_mode import KEY, Base, b64

HERE = os.path.dirname(os.path.abspath(__file__))


def tier_token(tier, plan="lifetime"):
    body = json.dumps({"feature": "platform", "tier": tier, "plan": plan, "iat": int(time.time()), "exp": None if plan == "lifetime" else int(time.time()) + 3600, "id": "t"}, separators=(",", ":")).encode()
    return "NXP1." + b64(body) + "." + b64(KEY.sign(b"NXP1." + body))


class FakeServer:
    """Stands in for the billing Worker so the desktop logic can be tested without a network."""
    def __init__(self):
        self.calls, self.claims, self.down, self.reply = [], {}, False, {}

    def __call__(self, method, url, headers=None, body=None):
        if self.down:
            raise OSError("offline")
        self.calls.append((method, url, headers, body))
        path = url.split("billing.example")[1]
        if path == "/checkout":
            if "checkout" in self.reply:
                return self.reply["checkout"]
            self.claims[body["claim"]] = body["claim_hash"]
            return 200, {"url": "https://checkout.stripe.com/c/pay/cs_test_1"}
        if path.startswith("/claim"):
            return self.reply.get("claim", (404, {"error": "unknown claim"}))
        if path == "/portal":
            return self.reply.get("portal", (200, {"url": "https://billing.stripe.com/p/s"}))
        return 404, {}


class BillingBase(Base):
    def setUp(self):
        super().setUp()
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        billing.STATE_PATH = os.path.join(d, "billing.json")
        billing.CONFIG_PATH = os.path.join(d, "billing_config.json")
        self.assertTrue(billing.STATE_PATH.startswith(d))
        os.environ["NEXXUS_BILLING_URL"] = "https://billing.example"
        self.addCleanup(os.environ.pop, "NEXXUS_BILLING_URL", None)
        self.srv = FakeServer()
        billing._transport = self.srv
        self.addCleanup(setattr, billing, "_transport", billing._http)


class CheckoutTest(BillingBase):
    def test_checkout_sends_only_a_hash_of_the_secret(self):
        out = billing.start_checkout("monthly")
        self.assertTrue(out["ok"])
        self.assertEqual(out["url"], "https://checkout.stripe.com/c/pay/cs_test_1")
        _, _, _, body = self.srv.calls[0]
        secret = json.load(open(billing.STATE_PATH))["secret"]
        self.assertEqual(body["claim_hash"], hashlib.sha256(secret.encode()).hexdigest())
        self.assertNotIn(secret, json.dumps(body), "the secret itself never leaves this computer at checkout time")
        self.assertEqual(billing.start_checkout("monthly")["ok"], True)
        self.assertEqual(len({c[3]["claim"] for c in self.srv.calls}), 1, "the same claim is reused, so a retry cannot create a second purchase identity")

    def test_unknown_plan_and_unconfigured_server(self):
        self.assertFalse(billing.start_checkout("gold")["ok"])
        del os.environ["NEXXUS_BILLING_URL"]
        out = billing.start_checkout("monthly")
        self.assertFalse(out["ok"])
        self.assertIn("not set up", out["message"])
        self.assertEqual(self.srv.calls, [], "nothing is contacted when billing is not configured")

    def test_only_https_server_addresses_are_used(self):
        os.environ["NEXXUS_BILLING_URL"] = "http://billing.example"
        self.assertEqual(billing.base_url(), "")

    def test_checkout_url_must_be_a_stripe_page(self):
        self.srv.reply["checkout"] = (200, {"url": "https://evil.example/pay"})
        self.assertFalse(billing.start_checkout("monthly")["ok"], "a redirect to a non-Stripe page is refused")
        self.srv.reply["checkout"] = (200, {"url": "javascript:alert(1)"})
        self.assertFalse(billing.start_checkout("lifetime")["ok"])

    def test_failures_are_plain_messages_and_never_raise(self):
        self.srv.down = True
        out = billing.start_checkout("monthly")
        self.assertFalse(out["ok"])
        self.assertIn("nothing was charged", out["message"])
        self.srv.down = False
        for status, text in ((429, "Too many"), (503, "still being set up"), (502, "Nothing was charged"), (409, "already have")):
            self.srv.reply["checkout"] = (status, {"error": "already active"} if status == 409 else {})
            self.assertIn(text, billing.start_checkout("monthly")["message"])


class RefreshTest(BillingBase):
    def test_paid_key_is_verified_offline_and_saved(self):
        billing.start_checkout("lifetime")
        self.srv.reply["claim"] = (200, {"state": "active", "plan": "lifetime", "token": tier_token("platform")})
        out = billing.refresh()
        self.assertTrue(out["ok"])
        self.assertTrue(out["entitlement"]["unlocked"])
        self.assertTrue(ent.is_unlocked())
        _, url, headers, _ = self.srv.calls[-1]
        self.assertIn("X-Claim-Secret", headers)
        self.assertNotIn("secret", url, "the secret travels in a header, never in the address")

    def test_a_forged_key_from_the_server_is_not_accepted(self):
        billing.start_checkout("lifetime")
        other = Ed25519PrivateKey.generate()
        body = json.dumps({"feature": "platform", "plan": "lifetime", "iat": 1, "exp": None, "id": "x"}, separators=(",", ":")).encode()
        forged = "NXP1." + b64(body) + "." + b64(other.sign(b"NXP1." + body))
        self.srv.reply["claim"] = (200, {"state": "active", "token": forged})
        out = billing.refresh()
        self.assertFalse(out["ok"])
        self.assertFalse(ent.is_unlocked())

    def test_nothing_ever_removes_a_licence_already_on_this_computer(self):
        ent.activate(tier_token("platform"))
        billing.start_checkout("monthly")
        for reply in ((404, {}), (500, {}), (200, {"state": "canceled"}), (200, {"state": "expired"})):
            self.srv.reply["claim"] = reply
            billing.refresh()
            self.assertTrue(ent.is_unlocked(), "a server hiccup or an abandoned checkout must not lock anyone out: %r" % (reply,))
        self.srv.down = True
        out = billing.refresh()
        self.assertFalse(out["ok"])
        self.assertTrue(out["entitlement"]["unlocked"])
        self.assertIn("unchanged", out["message"])

    def test_messages_for_every_state(self):
        billing.start_checkout("monthly")
        for state in ("pending", "past_due", "canceled", "expired", "failed", "revoked"):
            self.srv.reply["claim"] = (200, {"state": state})
            out = billing.refresh()
            self.assertEqual(out["message"], billing.MESSAGES[state])
            self.assertFalse(ent.is_unlocked())

    def test_refresh_before_any_purchase_contacts_nobody(self):
        out = billing.refresh()
        self.assertEqual(out["state"], "none")
        self.assertEqual(self.srv.calls, [])

    def test_portal_only_accepts_a_stripe_billing_page(self):
        billing.start_checkout("monthly")
        self.assertTrue(billing.portal()["ok"])
        self.srv.reply["portal"] = (200, {"url": "https://evil.example/"})
        self.assertFalse(billing.portal()["ok"])


class TierTest(Base):
    def test_unknown_tier_is_refused_enterprise_and_platform_accepted(self):
        self.assertFalse(ent.activate(tier_token("galaxy"))[0])
        self.assertFalse(ent.activate(tier_token("beta"))[0], "'beta' is a state of the app, not something a key can claim")
        self.assertTrue(ent.activate(tier_token("enterprise"))[0])

    def test_old_keys_without_a_tier_still_work_and_allows_matches_the_tier(self):
        from test_platform_mode import token
        self.assertTrue(ent.activate(token("lifetime"))[0])
        for feature in ("academy", "teams", "marketplace"):
            self.assertTrue(ent.allows(feature))
        self.assertFalse(ent.allows("something-new"))
        ent.remove()
        self.assertFalse(ent.allows("academy"), "no licence, no Platform areas")

    def test_beta_allows_everything_listed_and_ends_cleanly(self):
        open(ent.BETA_PATH, "w").write('{"beta_open": true}')
        self.assertTrue(ent.allows("marketplace"))
        open(ent.BETA_PATH, "w").write('{"beta_open": false}')
        self.assertFalse(ent.allows("marketplace"))

    def test_expired_monthly_key_unlocks_nothing(self):
        from test_platform_mode import token
        ent.activate(token("monthly", exp=int(time.time()) + 100))
        self.assertTrue(ent.allows("teams"))
        self.assertFalse(ent.allows("teams", now=time.time() + 1000))


class RouteTest(BillingBase):
    def setUp(self):
        super().setUp()
        self.local = True
        app = Flask(__name__)
        pm.register_routes(app, lambda: self.local, lambda p, s=200: (jsonify(p), s))
        self.c = app.test_client()

    def test_billing_works_while_locked_and_unlocks_after_payment(self):
        self.assertEqual(self.c.get("/api/platform/state").status_code, 402)
        r = self.c.post("/api/platform/billing/checkout", json={"plan": "monthly"})
        self.assertEqual((r.status_code, r.get_json()["url"][:25]), (200, "https://checkout.stripe.c"))
        self.srv.reply["claim"] = (200, {"state": "active", "plan": "monthly", "token": tier_token("platform", "monthly")})
        r = self.c.post("/api/platform/billing/refresh")
        self.assertTrue(r.get_json()["entitlement"]["unlocked"])
        self.assertEqual(self.c.get("/api/platform/state").status_code, 200)

    def test_errors_are_400_with_a_message_and_core_routes_are_untouched(self):
        self.srv.down = True
        r = self.c.post("/api/platform/billing/checkout", json={"plan": "monthly"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("message", r.get_json())
        self.assertEqual(self.c.get("/api/platform/entitlement").status_code, 200, "the pricing screen still loads")
        self.assertEqual(self.c.post("/api/platform/billing/nonsense").status_code, 404)

    def test_other_devices_cannot_use_billing(self):
        self.local = False
        self.assertEqual(self.c.post("/api/platform/billing/checkout", json={"plan": "monthly"}).status_code, 403)
        self.assertEqual(self.c.get("/api/platform/billing").status_code, 403)

    def test_summary_route(self):
        r = self.c.get("/api/platform/billing").get_json()
        self.assertTrue(r["configured"])
        self.assertEqual({p["id"] for p in r["plans"]}, {"monthly", "lifetime"})


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class CrossLanguageTest(Base):
    def test_token_signed_by_the_worker_verifies_in_python(self):
        der = KEY.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        script = ("import { signToken } from './relay/billing/worker.js';"
                  "console.log(await signToken({ LICENSE_PRIVATE_KEY_B64: process.env.K }, process.env.P, Number(process.env.E) || null));")
        for plan, exp in (("lifetime", ""), ("monthly", str(int(time.time()) + 3600))):
            out = subprocess.run(["node", "--input-type=module", "-e", script], cwd=HERE, capture_output=True, text=True, timeout=30,
                                 env={**os.environ, "K": base64.b64encode(der).decode(), "P": plan, "E": exp})
            self.assertEqual(out.returncode, 0, out.stderr)
            v = ent.verify(out.stdout.strip())
            self.assertTrue(v["valid"], v["reason"])
            self.assertEqual((v["plan"], v["tier"]), (plan, "platform"))
            self.assertTrue(ent.activate(out.stdout.strip())[0])
            ent.remove()


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class WorkerSuiteTest(unittest.TestCase):
    def test_node_suite_passes(self):
        out = subprocess.run(["node", os.path.join("relay", "billing", "test_billing_worker.mjs")], cwd=HERE, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


class BadgeTest(unittest.TestCase):
    def test_subscriber_badge_is_paid_only_and_uses_the_alpha_red(self):
        html = open(os.path.join(HERE, "axis-ui-interface", "project-X", "silo_vault", "render", "babylon_preview.html"), encoding="utf-8").read()
        self.assertIn("#ff3333", html)
        self.assertIn("e.beta || (e.plan !== 'monthly' && e.plan !== 'lifetime')", html, "no badge during Beta, when locked, or without a paid plan")
        self.assertNotIn("innerHTML = ent", html)


class HygieneTest(unittest.TestCase):
    def test_no_placeholder_handlers_or_secrets_in_the_billing_code(self):
        for rel in ("billing.py", os.path.join("relay", "billing", "worker.js"), os.path.join("tools", "stripe_setup.py")):
            text = open(os.path.join(HERE, rel), encoding="utf-8").read()
            for bad in ("example.com/checkout", "TODO", "FIXME", "mock_", "dummy"):
                self.assertNotIn(bad, text, "%s contains %r" % (rel, bad))
            self.assertIsNone(re.search(r"(sk|rk)_(live|test)_[A-Za-z0-9]{10,}|whsec_[A-Za-z0-9]{16,}", text), rel + " contains something shaped like a real Stripe secret")


if __name__ == "__main__":
    unittest.main()
