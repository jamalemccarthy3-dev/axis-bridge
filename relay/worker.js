// NEXXUS telemetry relay: a Cloudflare Worker that only QUEUES opt-in sandbox events until your desktop collects them.
//   POST /e     public: sandbox pages send {"events":[...]}; every event is checked against the fixed schema below
//   GET  /pull  private: the desktop fetches queued events (Authorization: Bearer <PULL_KEY>)
//   POST /ack   private: the desktop confirms the keys it stored; they are deleted
// It stores no IP address, no user agent and no free text. Bindings: KV namespace EVENTS_KV, secret PULL_KEY, variable ALLOWED_ORIGIN (your Pages origin, e.g. https://jamalemccarthy3-dev.github.io).
// The schema must match telemetry_hub.py (test_telemetry_hub.py checks that they agree).

const EVENTS = ["page_view", "install_clicked", "app_installed", "section_opened", "feedback_opened", "review_link_clicked", "error"];
const FIELDS = ["e", "t", "v", "i", "s", "w", "x"];
const ID = /^[0-9a-f]{32}$/, TAG = /^[a-z0-9_-]{1,32}$/, VER = /^[0-9a-z.\-]{1,16}$/;
const MAX_BODY = 4096, MAX_EVENTS = 20, TTL = 14 * 86400;

function valid(ev) {
  if (!ev || typeof ev !== "object" || Array.isArray(ev)) return false;
  const keys = Object.keys(ev);
  if (!keys.every((k) => FIELDS.includes(k)) || !("e" in ev && "t" in ev && "i" in ev)) return false;
  if (!EVENTS.includes(ev.e) || typeof ev.i !== "string" || !ID.test(ev.i)) return false;
  const now = Date.now() / 1000;
  if (typeof ev.t !== "number" || ev.t < now - 90 * 86400 || ev.t > now + 600) return false;
  if ("v" in ev && !(typeof ev.v === "string" && VER.test(ev.v))) return false;
  if ("s" in ev && !(ev.s === 0 || ev.s === 1)) return false;
  if ("w" in ev && !["s", "m", "l"].includes(ev.w)) return false;
  if ("x" in ev && !(typeof ev.x === "string" && TAG.test(ev.x))) return false;
  return true;
}

function same(a, b) {            // constant-time string compare
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const cors = { "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "null", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin" };
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

    if (url.pathname === "/e" && req.method === "POST") {
      if (req.headers.get("Origin") !== env.ALLOWED_ORIGIN) return new Response("forbidden", { status: 403, headers: cors });
      const text = await req.text();
      if (text.length > MAX_BODY) return new Response("too large", { status: 413, headers: cors });
      let body;
      try { body = JSON.parse(text); } catch (_) { return new Response("bad json", { status: 400, headers: cors }); }
      const list = body && Array.isArray(body.events) ? body.events.slice(0, MAX_EVENTS) : [];
      const good = list.filter(valid);
      await Promise.all(good.map((ev) => env.EVENTS_KV.put("ev:" + Date.now() + ":" + crypto.randomUUID().slice(0, 8), JSON.stringify(ev), { expirationTtl: TTL })));
      return new Response(null, { status: 204, headers: cors });
    }

    const auth = (req.headers.get("Authorization") || "").replace(/^Bearer /, "");
    if ((url.pathname === "/pull" || url.pathname === "/ack") && !same(auth, env.PULL_KEY || "")) return new Response("unauthorized", { status: 401 });

    if (url.pathname === "/pull" && req.method === "GET") {
      const listed = await env.EVENTS_KV.list({ prefix: "ev:", limit: 100 });
      const events = [];
      for (const k of listed.keys) {
        const v = await env.EVENTS_KV.get(k.name);
        if (v) { try { events.push({ k: k.name, ev: JSON.parse(v) }); } catch (_) { events.push({ k: k.name, ev: null }); } }
      }
      return Response.json({ events });
    }

    if (url.pathname === "/ack" && req.method === "POST") {
      const body = await req.json().catch(() => ({}));
      const keys = Array.isArray(body.keys) ? body.keys.filter((k) => typeof k === "string" && k.startsWith("ev:")).slice(0, 500) : [];
      await Promise.all(keys.map((k) => env.EVENTS_KV.delete(k)));
      return Response.json({ deleted: keys.length });
    }
    return new Response("not found", { status: 404 });
  },
};
