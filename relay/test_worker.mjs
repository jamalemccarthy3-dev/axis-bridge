// Run with: node relay/test_worker.mjs   (no dependencies; fakes the Cloudflare bindings)
import worker from "./worker.js";
import assert from "node:assert/strict";

const ORIGIN = "https://example.github.io";
const kv = new Map();
const env = (over = {}) => ({
  ALLOWED_ORIGIN: ORIGIN, PULL_KEY: "k".repeat(16),
  EVENTS_KV: { put: async (k, v) => kv.set(k, v), get: async (k) => kv.get(k) ?? null, delete: async (k) => kv.delete(k), list: async () => ({ keys: [...kv.keys()].map((name) => ({ name })) }) },
  ...over,
});
const limiter = (n) => { let c = 0; return { limit: async () => ({ success: ++c <= n }) }; };
const good = () => ({ e: "page_view", t: Math.floor(Date.now() / 1000), i: "a".repeat(32) });
const post = (body, e) => worker.fetch(new Request("https://r.example/e", { method: "POST", headers: { Origin: ORIGIN, "CF-Connecting-IP": "1.2.3.4" }, body: JSON.stringify(body) }), e);

let r = await post({ events: [good(), { ...good(), text: "x" }, { ...good(), e: "bogus" }] }, env());
assert.equal(r.status, 204); assert.equal(kv.size, 1, "only the valid event is queued");

r = await worker.fetch(new Request("https://r.example/e", { method: "POST", headers: { Origin: "https://evil.example" }, body: "{}" }), env());
assert.equal(r.status, 403);

kv.clear(); const lim = env({ PER_CLIENT_LIMITER: limiter(2) });
assert.equal((await post({ events: [good()] }, lim)).status, 204);
assert.equal((await post({ events: [good()] }, lim)).status, 204);
r = await post({ events: [good()] }, lim); assert.equal(r.status, 429); assert.equal(r.headers.get("Retry-After"), "60"); assert.equal(kv.size, 2, "limited request stores nothing");

const glob = env({ GLOBAL_LIMITER: limiter(0) }); assert.equal((await post({ events: [good()] }, glob)).status, 429);

kv.clear(); r = await post({ events: [good()] }, env({ PAUSE: "1" })); assert.equal(r.status, 503); assert.equal(kv.size, 0);

assert.equal((await worker.fetch(new Request("https://r.example/pull"), env())).status, 401, "pull needs the key");
const ok = await worker.fetch(new Request("https://r.example/pull", { headers: { Authorization: "Bearer " + "k".repeat(16) } }), env({ PAUSE: "1" }));
assert.equal(ok.status, 200, "the desktop can still pull while paused");
console.log("relay worker: all checks passed");
