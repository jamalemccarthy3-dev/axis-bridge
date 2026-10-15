# Billing: the Platform subscription pipeline

Platform costs **$9.99 / month** or **$199 once** (Lifetime Access Pass) after Beta. This page is the design, the audit result, and the steps the owner takes to go live. Nothing in this repo contains a Stripe key; **you** supply those, and the code cannot be tested against live Stripe without them.

## How it works

```
NEXXUS (your computer)            Billing Worker (Cloudflare, yours)             Stripe
  Buy ──POST /checkout (claim id + SHA-256 of a secret)──►  create Checkout Session ──►  hosted payment page
  ◄── https://checkout.stripe.com/... ───────────────────┘                                     │
                                                           ◄── signed webhooks ────────────────┘
  Check my subscription ──GET /claim (secret in a header)──► state + signed licence key (while paid)
  key verified OFFLINE against license_public_key.pem, saved locally
```

* **No account, no card on your computer.** The claim id/secret are random values created on first Buy (`nexxus_data/state/billing.json`, gitignored). The Worker stores only the secret's hash, so a claim cannot be hijacked or read by anyone else.
* **The webhook is public, so it lives in the Worker, not in the desktop app.** The desktop never accepts inbound connections; it only pulls.
* **Keys expire by themselves.** A monthly key lasts to the end of the paid period plus 3 days of grace. A failed renewal does not extend it, so non-payment simply ends access with no revoke call that could be missed. A network problem never removes a key already on the computer.

## Webhooks handled (all signature-verified before anything is read)

| Event | Effect |
|---|---|
| `checkout.session.completed` / `async_payment_succeeded` | paid: active (an unpaid, still-clearing session stays *pending*) |
| `checkout.session.async_payment_failed` | *failed*, no key |
| `checkout.session.expired` | an abandoned checkout becomes *expired*; nothing was charged |
| `customer.subscription.created` / `updated` | sets the paid-through date; `cancel_at_period_end` is shown; `past_due`, `canceled`, `unpaid` are mapped |
| `customer.subscription.deleted` | access ends now |
| `invoice.paid` | extends the period |
| `invoice.payment_failed` | *past due*: keeps what was paid for, extends nothing |
| `charge.refunded` (lifetime), `charge.dispute.created` | *revoked* |

Signature scheme: `Stripe-Signature: t=...,v1=HMAC_SHA256(secret, "t.body")`, constant-time compared, 5-minute tolerance (replays refused). Each event id is processed once (Stripe retries are acknowledged as duplicates); a processing error returns 500 so Stripe retries.

## Failure handling (NEXXUS core is never locked)

Only Platform areas ask whether a licence is valid; core NEXXUS never does. Declined card: Stripe's page handles it and offers another; no key is issued. Expired or abandoned checkout: *expired*, press Buy again. Closed tab / interrupted checkout: returning to the dialog (or pressing **Check my subscription**) picks up whatever Stripe confirmed. Server unreachable, not configured, Stripe down: a plain message, current access unchanged. Past-due subscribers keep access to the end of the paid period. **Manage billing** opens Stripe's customer portal (update card, cancel).

## Audit of placeholders (what was replaced)

| Found | Action |
|---|---|
| `NEXXUS_CHECKOUT_MONTHLY/LIFETIME` env "checkout links" and the "Checkout not set up yet" button | **removed**; Buy now creates a real Checkout Session through the Worker |
| Manual "owner emails you a key" step | replaced by webhook-driven issuing (manual keys still work) |
| No webhook listener existed | added `relay/billing/worker.js` |
| `relay/billing/wrangler.toml` `REPLACE_WITH_*` ids | **intentional config slots** for values only you have (KV id, price ids); the Worker answers 503 "not fully configured" until they are real |
| Marketplace seller `checkout_url` | **not** part of the Platform subscription. Sellers' product sales still use a link the administrator sets; real payouts and the 5% share need a payment provider that can split funds (Stripe Connect) and a lawyer-reviewed agreement. Not built. |
| Enterprise tier | `entitlements.TIERS` accepts a signed `"tier": "enterprise"` key and `allows(feature)` checks it, but nothing sells it and no price exists yet |

Tests: `test_billing.py` (desktop, tiers, routes, cross-language token check) and `relay/billing/test_billing_worker.mjs` (signatures, lifecycle, duplicates, hijack attempts), run by `python test_billing.py`.

## Going live (owner steps)

1. **Stripe account**, start in **test mode**. Create a *restricted* key (Checkout Sessions: write, Customer portal: write, Customers: read).
2. **Worker:** `cd relay/billing`, `npx wrangler kv namespace create BILLING_KV` and paste the id into `wrangler.toml`.
3. `STRIPE_SECRET_KEY=sk_test_... python tools/stripe_setup.py --worker-url https://<your-worker>` shows the plan; add `--apply` to create the product, both prices and the webhook. Put the two price ids in `wrangler.toml`.
4. Secrets (never in a file): `npx wrangler secret put STRIPE_SECRET_KEY`, `... STRIPE_WEBHOOK_SECRET` (printed once by the setup tool), and `python tools/issue_license.py export-b64 | npx wrangler secret put LICENSE_PRIVATE_KEY_B64`.
5. `npx wrangler deploy`. Host a `success.html` and `cancel.html` (GitHub Pages is fine) and set `SUCCESS_URL` / `CANCEL_URL`.
6. On the NEXXUS computer set `NEXXUS_BILLING_URL=https://<your-worker>` (or `billing_config.json` `{"url": "..."}`).
7. Test with Stripe's test card `4242 4242 4242 4242`, then a decline card `4000 0000 0000 0002`, then cancel from Manage billing.
8. Repeat steps 1, 3 and 4 with live keys. End Beta by setting `platform_beta.json` to `{"beta_open": false}`.

## Honest limits

* The licence check is local, in source-available software: someone who edits the code can bypass it. Real enforcement needs a server for each networked feature.
* Tax, invoices, refunds policy, and the terms you sell under are yours to set up (Stripe Tax: set `AUTOMATIC_TAX = "1"` once configured). Check the rules where you and your customers live.
* Restricted Stripe keys and the licence signing key are the crown jewels: anyone holding the latter can mint keys. Back it up, never commit it.
