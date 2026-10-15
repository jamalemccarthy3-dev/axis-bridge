// Run with: node relay/billing/test_billing_worker.mjs   (no dependencies; fakes KV and the Stripe API, signs webhooks exactly as Stripe does)
import worker, { verifyStripeSignature, signToken } from "./worker.js";
import assert from "node:assert/strict";
import { createHmac, createHash, generateKeyPairSync, verify as edVerify } from "node:crypto";

const WHSEC = "whsec_test_secret";
const kv = new Map();
const KV = { get: async (k) => kv.get(k) ?? null, put: async (k, v) => { kv.set(k, v); }, delete: async (k) => kv.delete(k) };
const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const env = (over = {}) => ({ BILLING_KV: KV, STRIPE_SECRET_KEY: "sk_test_x", STRIPE_WEBHOOK_SECRET: WHSEC, LICENSE_PRIVATE_KEY_B64: privateKey.export({ type: "pkcs8", format: "der" }).toString("base64"),
  PRICE_MONTHLY: "price_m", PRICE_LIFETIME: "price_l", SUCCESS_URL: "https://ok.example/s", CANCEL_URL: "https://ok.example/c", ...over });
const now = () => Math.floor(Date.now() / 1000);
const sha = (s) => createHash("sha256").update(s).digest("hex");

const stripeCalls = [];
globalThis.fetch = async (url, init) => {                       // the only outbound call the Worker makes is to Stripe
  stripeCalls.push({ url, body: init.body, headers: init.headers });
  if (String(url).endsWith("/checkout/sessions")) return new Response(JSON.stringify({ id: "cs_1", url: "https://checkout.stripe.com/c/pay/cs_1" }), { status: 200 });
  if (String(url).endsWith("/billing_portal/sessions")) return new Response(JSON.stringify({ url: "https://billing.stripe.com/p/s_1" }), { status: 200 });
  return new Response(JSON.stringify({ error: { message: "nope" } }), { status: 400 });
};

const sign = (body, secret = WHSEC, t = now()) => "t=" + t + ",v1=" + createHmac("sha256", secret).update(t + "." + body).digest("hex");
const hook = (event, header, e = env()) => { const body = JSON.stringify(event); return worker.fetch(new Request("https://b.example/webhook", { method: "POST", headers: { "Stripe-Signature": header ?? sign(body) }, body }), e); };
const req = (path, method, body, headers = {}, e = env()) => worker.fetch(new Request("https://b.example" + path, { method, headers: { "CF-Connecting-IP": "9.9.9.9", ...headers }, body: body ? JSON.stringify(body) : undefined }), e);
const claimOf = (id, secret) => req("/claim?claim=" + id, "GET", null, { "X-Claim-Secret": secret });
const decode = (tok) => JSON.parse(Buffer.from(tok.split(".")[1], "base64url").toString());

// ---- signature scheme
const body = '{"id":"evt_1"}';
assert.equal(await verifyStripeSignature(body, sign(body), WHSEC), true);
assert.equal(await verifyStripeSignature(body, sign(body, "whsec_other"), WHSEC), false, "wrong secret");
assert.equal(await verifyStripeSignature(body + " ", sign(body), WHSEC), false, "tampered body");
assert.equal(await verifyStripeSignature(body, sign(body, WHSEC, now() - 3600), WHSEC), false, "replayed old event");
assert.equal(await verifyStripeSignature(body, "garbage", WHSEC), false);
assert.equal(await verifyStripeSignature(body, sign(body), ""), false, "no secret configured fails closed");
assert.equal(await verifyStripeSignature(body, "t=" + now() + ",v1=", WHSEC), false);

// ---- unsigned / forged webhooks change nothing
let r = await hook({ id: "evt_x", type: "checkout.session.completed", data: { object: {} } }, "t=1,v1=00");
assert.equal(r.status, 400); assert.equal(kv.size, 0);
r = await worker.fetch(new Request("https://b.example/webhook", { method: "POST", body: "{}" }), env());
assert.equal(r.status, 400, "no signature header");

// ---- checkout
const CLAIM = "a1b2c3d4e5f60718293a4b5c", SECRET = "s".repeat(48), HASH = sha(SECRET);
r = await req("/checkout", "POST", { plan: "monthly", claim: CLAIM, claim_hash: HASH });
assert.equal(r.status, 200); assert.equal((await r.json()).url, "https://checkout.stripe.com/c/pay/cs_1");
const sent = new URLSearchParams(stripeCalls.at(-1).body);
assert.equal(sent.get("mode"), "subscription"); assert.equal(sent.get("line_items[0][price]"), "price_m"); assert.equal(sent.get("client_reference_id"), CLAIM);
assert.match(sent.get("success_url"), /^https:\/\/ok\.example\/s\?session_id=\{CHECKOUT_SESSION_ID\}$/); assert.equal(sent.get("cancel_url"), "https://ok.example/c");
assert.ok(!stripeCalls.at(-1).body.includes(SECRET), "the claim secret never leaves the Worker's request");
assert.equal(stripeCalls.at(-1).headers.Authorization, "Bearer sk_test_x");
for (const bad of [{ plan: "gold", claim: CLAIM, claim_hash: HASH }, { plan: "monthly", claim: "x", claim_hash: HASH }, { plan: "monthly", claim: CLAIM, claim_hash: "zz" }, {}]) assert.equal((await req("/checkout", "POST", bad)).status, 400);
assert.equal((await req("/checkout", "POST", { plan: "monthly", claim: CLAIM, claim_hash: sha("someone else") })).status, 409, "a claim id cannot be taken over");
assert.equal((await req("/checkout", "POST", { plan: "monthly", claim: "f".repeat(24), claim_hash: HASH }, {}, env({ PRICE_MONTHLY: "" }))).status, 503, "half-configured server says so");
assert.equal((await req("/checkout", "POST", { plan: "monthly", claim: "e".repeat(24), claim_hash: HASH }, {}, env({ SUCCESS_URL: "http://insecure.example" }))).status, 503, "https redirect pages only");
const failing = globalThis.fetch; globalThis.fetch = async () => new Response("{}", { status: 500 });
assert.equal((await req("/checkout", "POST", { plan: "lifetime", claim: "d".repeat(24), claim_hash: HASH })).status, 502, "Stripe outage -> clean error");
globalThis.fetch = failing;

// ---- before payment: nothing to claim, no key
r = await claimOf(CLAIM, SECRET); let c = await r.json();
assert.equal(c.state, "pending"); assert.equal(c.token, undefined, "no key before payment");
assert.equal((await claimOf(CLAIM, "wrong")).status, 404, "wrong secret looks like an unknown claim");
assert.equal((await claimOf("0".repeat(24), SECRET)).status, 404);
assert.equal((await req("/claim?claim=" + CLAIM, "GET")).status, 404, "no secret");

// ---- subscription lifecycle
const periodEnd = now() + 30 * 86400;
const completed = { id: "evt_a", type: "checkout.session.completed", data: { object: { id: "cs_1", mode: "subscription", client_reference_id: CLAIM, payment_status: "paid", customer: "cus_1", subscription: "sub_1" } } };
assert.equal((await hook(completed)).status, 200);
assert.equal((await (await hook(completed)).json()).duplicate, true, "a retried event is processed once");
c = await (await claimOf(CLAIM, SECRET)).json();
assert.equal(c.state, "active"); assert.equal(c.plan, "monthly"); assert.ok(c.token.startsWith("NXP1."));
let p = decode(c.token); assert.equal(p.feature, "platform"); assert.equal(p.tier, "platform"); assert.equal(p.plan, "monthly"); assert.ok(p.exp > now());
const signedPart = c.token.split(".");
assert.equal(edVerify(null, Buffer.from("NXP1." + Buffer.from(signedPart[1], "base64url").toString()), publicKey, Buffer.from(signedPart[2], "base64url")), true, "token verifies with the public key");

await hook({ id: "evt_b", type: "customer.subscription.updated", data: { object: { object: "subscription", id: "sub_1", customer: "cus_1", status: "active", current_period_end: periodEnd, cancel_at_period_end: true, metadata: { claim: CLAIM } } } });
c = await (await claimOf(CLAIM, SECRET)).json();
assert.equal(c.cancel_at_period_end, true); assert.ok(Math.abs(decode(c.token).exp - (periodEnd + 3 * 86400)) < 5, "key lasts to the end of the paid period plus grace");

await hook({ id: "evt_c", type: "invoice.payment_failed", data: { object: { subscription: "sub_1" } } });       // found through the stored subscription id
c = await (await claimOf(CLAIM, SECRET)).json();
assert.equal(c.state, "past_due"); assert.ok(c.token, "a failed renewal does not cut off access already paid for");
assert.ok(Math.abs(decode(c.token).exp - (periodEnd + 3 * 86400)) < 5, "and does not extend it either");

await hook({ id: "evt_d", type: "invoice.paid", data: { object: { subscription: "sub_1", lines: { data: [{ period: { end: periodEnd + 30 * 86400 } }] } } } });
c = await (await claimOf(CLAIM, SECRET)).json();
assert.equal(c.state, "active"); assert.ok(decode(c.token).exp > periodEnd + 30 * 86400);

await hook({ id: "evt_e", type: "customer.subscription.deleted", data: { object: { object: "subscription", id: "sub_1", metadata: { claim: CLAIM } } } });
c = await (await claimOf(CLAIM, SECRET)).json();
assert.equal(c.state, "canceled"); assert.equal(c.token, undefined, "ended subscription: no key");

// ---- abandoned / declined / async checkouts
const C2 = "b".repeat(24), S2 = "t".repeat(40);
await req("/checkout", "POST", { plan: "monthly", claim: C2, claim_hash: sha(S2) });
await hook({ id: "evt_f", type: "checkout.session.expired", data: { object: { id: "cs_2", client_reference_id: C2 } } });
c = await (await claimOf(C2, S2)).json(); assert.equal(c.state, "expired"); assert.equal(c.token, undefined);
await req("/checkout", "POST", { plan: "monthly", claim: C2, claim_hash: sha(S2) });                    // the person simply tries again
c = await (await claimOf(C2, S2)).json(); assert.equal(c.state, "pending");
await hook({ id: "evt_g", type: "checkout.session.completed", data: { object: { client_reference_id: C2, mode: "subscription", payment_status: "unpaid", subscription: "sub_2" } } });
c = await (await claimOf(C2, S2)).json(); assert.equal(c.state, "pending"); assert.equal(c.token, undefined, "an unpaid (still clearing) session gives no key");
await hook({ id: "evt_h", type: "checkout.session.async_payment_failed", data: { object: { client_reference_id: C2 } } });
c = await (await claimOf(C2, S2)).json(); assert.equal(c.state, "failed"); assert.equal(c.token, undefined);

// ---- lifetime, refund
const C3 = "c".repeat(24), S3 = "u".repeat(40);
await req("/checkout", "POST", { plan: "lifetime", claim: C3, claim_hash: sha(S3) });
assert.equal(new URLSearchParams(stripeCalls.at(-1).body).get("mode"), "payment");
await hook({ id: "evt_i", type: "checkout.session.completed", data: { object: { client_reference_id: C3, mode: "payment", payment_status: "paid", customer: "cus_3", payment_intent: "pi_3" } } });
c = await (await claimOf(C3, S3)).json(); assert.equal(c.plan, "lifetime"); assert.equal(decode(c.token).exp, null);
assert.equal((await req("/checkout", "POST", { plan: "lifetime", claim: C3, claim_hash: sha(S3) })).status, 409, "no double purchase");
await hook({ id: "evt_j", type: "charge.refunded", data: { object: { payment_intent: "pi_3", refunded: true } } });
c = await (await claimOf(C3, S3)).json(); assert.equal(c.state, "revoked"); assert.equal(c.token, undefined);

// ---- events for unknown claims are acknowledged and ignored, a broken handler asks Stripe to retry
assert.equal((await hook({ id: "evt_k", type: "invoice.payment_failed", data: { object: { subscription: "sub_unknown" } } })).status, 200);
const broken = { BILLING_KV: { ...KV, get: async () => { throw new Error("kv down"); } } };
assert.equal((await hook({ id: "evt_l", type: "invoice.paid", data: { object: { client_reference_id: CLAIM } } }, undefined, env(broken))).status, 500);

// ---- portal
r = await req("/portal", "POST", { claim: CLAIM, secret: SECRET }); assert.equal(r.status, 200); assert.equal((await r.json()).url, "https://billing.stripe.com/p/s_1");
assert.equal((await req("/portal", "POST", { claim: CLAIM, secret: "wrong" })).status, 404);

// ---- rate limiting and routing
const lim = { limit: async () => ({ success: false }) };
assert.equal((await req("/checkout", "POST", { plan: "monthly", claim: CLAIM, claim_hash: HASH }, {}, env({ CHECKOUT_LIMITER: lim }))).status, 429);
assert.equal((await req("/health", "GET")).status, 200); assert.equal((await req("/nope", "GET")).status, 404);

// ---- a bare signToken call is usable by the cross-language test
assert.ok((await signToken(env(), "lifetime", null)).startsWith("NXP1."));
console.log("billing worker: all checks passed");
