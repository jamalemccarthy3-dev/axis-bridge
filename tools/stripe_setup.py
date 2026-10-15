"""stripe_setup.py - one-time owner tool: creates the two Platform prices and the webhook endpoint in YOUR Stripe account.

    set STRIPE_SECRET_KEY=sk_test_...        (the key comes from your environment only; it is never a command-line argument and never printed)
    python tools/stripe_setup.py --worker-url https://nexxus-billing.<you>.workers.dev            (shows what it would create, changes nothing)
    python tools/stripe_setup.py --worker-url https://... --apply                                  (creates it)

It prints the two price ids (for wrangler.toml) and, once, the webhook signing secret (for `wrangler secret put STRIPE_WEBHOOK_SECRET`). Use a TEST-mode key first. Run it again with a live key to go live:
objects are created fresh in whichever mode the key belongs to. Re-running with --apply creates duplicates, so use it once per mode.
"""
import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import json

API = "https://api.stripe.com/v1/"
EVENTS = ["checkout.session.completed", "checkout.session.async_payment_succeeded", "checkout.session.async_payment_failed", "checkout.session.expired",
          "customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted", "invoice.paid", "invoice.payment_failed", "charge.refunded", "charge.dispute.created"]
PRODUCT = "NEXXUS Platform"
PRICES = [("monthly", 999, {"recurring[interval]": "month"}, "NEXXUS Platform, monthly"), ("lifetime", 19900, {}, "NEXXUS Platform, lifetime access pass")]


def call(key, path, form):
    req = urllib.request.Request(API + path, data=urllib.parse.urlencode(form).encode(), method="POST", headers={"Authorization": "Bearer " + key, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read())["error"]["message"]
        except Exception:
            msg = "HTTP %d" % e.code
        raise SystemExit("Stripe refused the request: " + msg)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worker-url", required=True, help="the https address of the deployed billing Worker")
    ap.add_argument("--apply", action="store_true", help="actually create the objects (default: only show the plan)")
    a = ap.parse_args(argv)
    if not a.worker_url.startswith("https://"):
        raise SystemExit("The Worker address must start with https://")
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
        raise SystemExit("Set STRIPE_SECRET_KEY in your environment first (a test key to begin with).")
    mode = "LIVE" if "_live_" in key else "TEST"
    print("Mode: %s. Would create: product '%s', monthly price $9.99, lifetime price $199.00, and a webhook at %s/webhook for %d events." % (mode, PRODUCT, a.worker_url.rstrip("/"), len(EVENTS)))
    if not a.apply:
        print("Nothing was changed. Add --apply to create them.")
        return 0
    if mode == "LIVE" and input("This is a LIVE key. Type LIVE to continue: ").strip() != "LIVE":
        raise SystemExit("Cancelled.")
    product = call(key, "products", {"name": PRODUCT})
    ids = {}
    for plan, cents, extra, nick in PRICES:
        ids[plan] = call(key, "prices", {"product": product["id"], "unit_amount": str(cents), "currency": "usd", "nickname": nick, **extra})["id"]
    hook = call(key, "webhook_endpoints", {"url": a.worker_url.rstrip("/") + "/webhook", **{"enabled_events[%d]" % i: e for i, e in enumerate(EVENTS)}})
    print("\nPRICE_MONTHLY  = %s\nPRICE_LIFETIME = %s\n(put these in relay/billing/wrangler.toml)" % (ids["monthly"], ids["lifetime"]))
    print("\nWebhook signing secret (shown once; store it with `npx wrangler secret put STRIPE_WEBHOOK_SECRET`):\n%s" % hook.get("secret", "(not returned)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
