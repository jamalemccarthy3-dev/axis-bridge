// NEXXUS billing Worker: Stripe Checkout, Stripe webhooks and signed licence tokens.
//
//   POST /checkout   a NEXXUS asks for a Checkout Session for a plan. It sends only a random claim id and the SHA-256 of a claim secret it keeps.
//   POST /webhook    Stripe tells us what happened. The signature is verified before anything is read; events are processed once.
//   GET  /claim      the NEXXUS that holds the claim secret fetches its entitlement: state, and a signed licence token while access is paid for.
//   POST /portal     a Stripe customer-portal link so the customer can update a card or cancel.
//   GET  /health     "ok", nothing else.
//
// Nobody has an account. Nothing here ever sees a card number (Stripe Checkout collects it). A licence token is the same NXP1 token that tools/issue_license.py makes, signed with an Ed25519 key,
// so NEXXUS checks it offline against license_public_key.pem. A monthly token lasts to the end of the paid period plus a few days of grace, so if payments stop, access simply ends: there is no
// "revoke" call that can be missed. A network problem never removes access that was already paid for.
//
// Bindings: KV namespace BILLING_KV. Secrets: STRIPE_SECRET_KEY (use a restricted key: Checkout Sessions write, Billing Portal write, Customers read), STRIPE_WEBHOOK_SECRET (whsec_...),
// LICENSE_PRIVATE_KEY_B64 (base64 of the PKCS8 DER of the Ed25519 private key). Variables: PRICE_MONTHLY, PRICE_LIFETIME (Stripe price ids), SUCCESS_URL, CANCEL_URL (https pages you host),
// optional AUTOMATIC_TAX = "1". Optional rate-limit bindings: CHECKOUT_LIMITER, CLAIM_LIMITER.

const TOLERANCE_SECONDS = 300;
const GRACE_SECONDS = 3 * 86400;
const FALLBACK_PERIOD_SECONDS = 35 * 86400;
const SEEN_TTL = 7 * 86400;
const PLANS = ["monthly", "lifetime"];
const CLAIM_RE = /^[0-9a-f]{16,32}$/;
const HASH_RE = /^[0-9a-f]{64}$/;
const enc = new TextEncoder();

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const now = () => Math.floor(Date.now() / 1000);
const json = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

function sameString(a, b) {                       // constant-time compare of two strings
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

async function sha256Hex(text) { return hex(await crypto.subtle.digest("SHA-256", enc.encode(text))); }

async function hmacHex(secret, text) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", key, enc.encode(text)));
}

// ---------------------------------------------------------------- Stripe webhook signature (the scheme Stripe documents: t=<time>,v1=<hmac of "t.body">)
export async function verifyStripeSignature(body, header, secret, nowSeconds = now()) {
  if (!secret || typeof header !== "string" || typeof body !== "string") return false;
  const parts = header.split(",").map((p) => p.trim().split("="));
  const t = parts.find((p) => p[0] === "t");
  const sigs = parts.filter((p) => p[0] === "v1" && p[1]).map((p) => p[1]);
  if (!t || !/^\d+$/.test(t[1] || "") || !sigs.length) return false;
  if (Math.abs(nowSeconds - Number(t[1])) > TOLERANCE_SECONDS) return false;      // a replayed old event is refused
  const expected = await hmacHex(secret, t[1] + "." + body);
  return sigs.some((s) => sameString(s, expected));
}

// ---------------------------------------------------------------- licence tokens (identical in format to tools/issue_license.py)
export async function signToken(env, plan, exp) {
  const payload = JSON.stringify({ feature: "platform", tier: "platform", plan, iat: now(), exp: plan === "lifetime" ? null : exp, id: hex(crypto.getRandomValues(new Uint8Array(6))) });
  const der = Uint8Array.from(atob(env.LICENSE_PRIVATE_KEY_B64), (c) => c.charCodeAt(0));
  const key = await crypto.subtle.importKey("pkcs8", der, { name: "Ed25519" }, false, ["sign"]);
  const sig = await crypto.subtle.sign({ name: "Ed25519" }, key, enc.encode("NXP1." + payload));
  return "NXP1." + b64u(enc.encode(payload)) + "." + b64u(sig);
}

// ---------------------------------------------------------------- state
async function getClaim(env, claim) { const v = await env.BILLING_KV.get("claim:" + claim); return v ? JSON.parse(v) : null; }
async function putClaim(env, claim, rec) { await env.BILLING_KV.put("claim:" + claim, JSON.stringify(rec)); }

async function claimFor(env, obj) {
  const meta = (obj && obj.metadata) || {};
  let id = obj.client_reference_id || meta.claim || null;
  if (!id && obj.object === "subscription") id = await env.BILLING_KV.get("sub:" + obj.id);
  if (!id && obj.subscription) id = await env.BILLING_KV.get("sub:" + obj.subscription);
  if (!id && obj.payment_intent) id = await env.BILLING_KV.get("pi:" + obj.payment_intent);
  return id && CLAIM_RE.test(id) ? id : null;
}

function activate(rec, session) {
  const monthly = session.mode === "subscription";
  rec.plan = monthly ? "monthly" : "lifetime";
  rec.state = "active";
  rec.customer = session.customer || rec.customer || null;
  rec.subscription = session.subscription || rec.subscription || null;
  rec.payment_intent = session.payment_intent || rec.payment_intent || null;
  rec.exp = monthly ? Math.max(rec.exp || 0, now() + FALLBACK_PERIOD_SECONDS) : null;      // refined by the subscription events below
  rec.updated = now();
}

export async function handleEvent(env, event) {
  const obj = event.data && event.data.object;
  if (!obj) return "ignored";
  const claim = await claimFor(env, obj);
  const rec = claim ? await getClaim(env, claim) : null;
  const type = event.type;
  if (!rec) return "no claim";
  const note = (state) => { rec.state = state; rec.updated = now(); };

  if (type === "checkout.session.completed" || type === "checkout.session.async_payment_succeeded") {
    if (obj.payment_status === "paid" || obj.payment_status === "no_payment_required") activate(rec, obj);
    else { rec.pending_reason = "waiting for the payment to clear"; note("pending"); }                // a bank debit, for example, can take days
    if (obj.subscription) await env.BILLING_KV.put("sub:" + obj.subscription, claim);
    if (obj.payment_intent) await env.BILLING_KV.put("pi:" + obj.payment_intent, claim);
  } else if (type === "checkout.session.async_payment_failed") {
    note("failed");
  } else if (type === "checkout.session.expired") {
    if (rec.state === "pending") note("expired");                                                       // an abandoned checkout; nothing was charged
  } else if (type === "customer.subscription.created" || type === "customer.subscription.updated") {
    await env.BILLING_KV.put("sub:" + obj.id, claim);
    const end = obj.current_period_end ? obj.current_period_end + GRACE_SECONDS : now() + FALLBACK_PERIOD_SECONDS;
    rec.customer = obj.customer || rec.customer;
    rec.subscription = obj.id;
    rec.cancel_at_period_end = !!obj.cancel_at_period_end;
    if (obj.status === "active" || obj.status === "trialing") { rec.plan = "monthly"; rec.exp = end; note("active"); }
    else if (obj.status === "past_due") note("past_due");                                               // access continues only to the end of what was paid for
    else if (obj.status === "canceled" || obj.status === "unpaid" || obj.status === "incomplete_expired") { rec.exp = Math.min(rec.exp || now(), now()); note("canceled"); }
  } else if (type === "customer.subscription.deleted") {
    rec.exp = Math.min(rec.exp || now(), now());
    note("canceled");
  } else if (type === "invoice.payment_failed") {
    if (rec.plan === "monthly") { rec.last_failure = now(); note("past_due"); }                         // the exp is NOT extended: if it stays unpaid, access ends on its own
  } else if (type === "invoice.paid" || type === "invoice.payment_succeeded") {
    const line = obj.lines && obj.lines.data && obj.lines.data[0];
    const end = line && line.period && line.period.end ? line.period.end + GRACE_SECONDS : now() + FALLBACK_PERIOD_SECONDS;
    if (rec.plan === "monthly") { rec.exp = Math.max(rec.exp || 0, end); note("active"); }
  } else if (type === "charge.refunded" || type === "charge.dispute.created") {
    if (type === "charge.dispute.created" || obj.refunded === true) { if (rec.plan === "lifetime" || type === "charge.dispute.created") note("revoked"); }
  } else return "ignored";
  await putClaim(env, claim, rec);
  return "processed " + type;
}

// ---------------------------------------------------------------- Stripe API (form encoded, never logged)
async function stripe(env, path, form, idem) {
  const headers = { Authorization: "Bearer " + env.STRIPE_SECRET_KEY, "Content-Type": "application/x-www-form-urlencoded" };
  if (idem) headers["Idempotency-Key"] = idem;
  const r = await fetch("https://api.stripe.com/v1/" + path, { method: "POST", headers, body: new URLSearchParams(form).toString() });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data.error && data.error.message) || "Stripe refused the request");
  return data;
}

function httpsUrl(u) { try { const x = new URL(u); return x.protocol === "https:" ? x.toString() : null; } catch (_) { return null; } }

async function limited(env, name, key) {
  const l = env[name];
  return l ? !(await l.limit({ key })).success : false;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const ip = req.headers.get("CF-Connecting-IP") || "unknown";

    if (url.pathname === "/health") return new Response("ok");

    if (url.pathname === "/webhook" && req.method === "POST") {
      const body = await req.text();
      if (body.length > 256 * 1024) return json({ error: "too large" }, 413);
      if (!(await verifyStripeSignature(body, req.headers.get("Stripe-Signature"), env.STRIPE_WEBHOOK_SECRET))) return json({ error: "bad signature" }, 400);      // nothing is read before this passes
      let event;
      try { event = JSON.parse(body); } catch (_) { return json({ error: "bad json" }, 400); }
      if (!event || typeof event.id !== "string") return json({ error: "bad event" }, 400);
      try {
        if (await env.BILLING_KV.get("evt:" + event.id)) return json({ ok: true, duplicate: true });                  // Stripe retries: each event counts once
        const result = await handleEvent(env, event);
        await env.BILLING_KV.put("evt:" + event.id, "1", { expirationTtl: SEEN_TTL });
        return json({ ok: true, result });
      } catch (e) { return json({ error: "processing failed" }, 500); }                                              // 500 makes Stripe retry later
    }

    if (url.pathname === "/checkout" && req.method === "POST") {
      if (await limited(env, "CHECKOUT_LIMITER", ip)) return json({ error: "slow down" }, 429);
      let d;
      try { d = JSON.parse(await req.text()); } catch (_) { return json({ error: "bad json" }, 400); }
      if (!d || !PLANS.includes(d.plan) || !CLAIM_RE.test(d.claim || "") || !HASH_RE.test(d.claim_hash || "")) return json({ error: "bad request" }, 400);
      const success = httpsUrl(env.SUCCESS_URL), cancel = httpsUrl(env.CANCEL_URL);
      const price = d.plan === "monthly" ? env.PRICE_MONTHLY : env.PRICE_LIFETIME;
      if (!success || !cancel || !price) return json({ error: "billing is not fully configured on the server" }, 503);
      const existing = await getClaim(env, d.claim);
      if (existing && !sameString(existing.hash, d.claim_hash)) return json({ error: "that claim belongs to someone else" }, 409);     // a claim id cannot be hijacked
      if (existing && existing.state === "active" && existing.plan === d.plan) return json({ error: "already active" }, 409);
      const form = { mode: d.plan === "monthly" ? "subscription" : "payment", "line_items[0][price]": price, "line_items[0][quantity]": "1", client_reference_id: d.claim,
                     "metadata[claim]": d.claim, "metadata[plan]": d.plan, success_url: success + (success.includes("?") ? "&" : "?") + "session_id={CHECKOUT_SESSION_ID}", cancel_url: cancel,
                     expires_at: String(now() + 7200), allow_promotion_codes: "true" };
      if (d.plan === "monthly") form["subscription_data[metadata][claim]"] = d.claim;
      else { form["payment_intent_data[metadata][claim]"] = d.claim; form.customer_creation = "always"; }
      if (env.AUTOMATIC_TAX === "1") form["automatic_tax[enabled]"] = "true";
      let session;
      try { session = await stripe(env, "checkout/sessions", form, "nx-" + d.claim + "-" + d.plan + "-" + Math.floor(now() / 600)); }
      catch (e) { return json({ error: "could not start checkout" }, 502); }
      await putClaim(env, d.claim, { hash: d.claim_hash, plan: d.plan, state: "pending", session: session.id, created: now(), updated: now(), exp: null });
      return json({ url: session.url });
    }

    if (url.pathname === "/claim" && req.method === "GET") {
      if (await limited(env, "CLAIM_LIMITER", ip)) return json({ error: "slow down" }, 429);
      const id = url.searchParams.get("claim") || "";
      const rec = CLAIM_RE.test(id) ? await getClaim(env, id) : null;
      const secret = req.headers.get("X-Claim-Secret") || "";
      if (!rec || !secret || !sameString(await sha256Hex(secret), rec.hash)) return json({ error: "unknown claim" }, 404);
      const out = { state: rec.state, plan: rec.plan, exp: rec.exp, cancel_at_period_end: !!rec.cancel_at_period_end };
      const paid = (rec.state === "active" || rec.state === "past_due") && (rec.plan === "lifetime" || (rec.exp && rec.exp > now()));
      if (paid) out.token = await signToken(env, rec.plan, rec.exp);
      return json(out);
    }

    if (url.pathname === "/portal" && req.method === "POST") {
      if (await limited(env, "CLAIM_LIMITER", ip)) return json({ error: "slow down" }, 429);
      let d;
      try { d = JSON.parse(await req.text()); } catch (_) { return json({ error: "bad json" }, 400); }
      const rec = d && CLAIM_RE.test(d.claim || "") ? await getClaim(env, d.claim) : null;
      if (!rec || !d.secret || !sameString(await sha256Hex(d.secret), rec.hash) || !rec.customer) return json({ error: "unknown claim" }, 404);
      try {
        const s = await stripe(env, "billing_portal/sessions", { customer: rec.customer, return_url: httpsUrl(env.SUCCESS_URL) || "https://stripe.com" });
        return json({ url: s.url });
      } catch (e) { return json({ error: "could not open the billing portal" }, 502); }
    }

    return json({ error: "not found" }, 404);
  },
};
