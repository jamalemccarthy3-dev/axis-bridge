# NEXXUS architecture audit: mesh vs. multi-agent orchestration patterns

Date: 2026-10-13. Scope: how NEXXUS passes messages between engines, routes through the hub and verifies state, compared with the usual enterprise multi-agent patterns (a root orchestrator, context-isolated
subagents, stateless tool dispatch). Everything under "Evidence" was read in the code or measured on this PC; numbers marked *(under load)* were taken while the verification suite was running, so absolute
values are inflated and the ratios are what matter. Guardrail honoured: no working core function was changed except two additive fixes listed in section 5.

## 1. What NEXXUS actually is (from the code)

| Piece | Where | Behaviour |
|---|---|---|
| Hub | `python_server.py` routes `/api/mesh/*`, logic in `mesh_bridge.py` | Flask, threaded. Holds liveness (`_LIVE`), last probes (`_LAST`), map version/awareness, message log. All in memory except the log. |
| Engines | 21 `mesh.py` copies, each in a `cmd` window titled `ENGINE <name>` | Long-lived process that sends a signed heartbeat every ~10 s. The same file answers `--mesh` one-shot requests. |
| Calls into an engine | `mesh_bridge._run_engine` | **Spawns a fresh `python mesh.py --mesh` per call** (stdin JSON in, last stdout line JSON out, timeout kills it). The hub never talks to the running engine. |
| Engine to engine | `POST /api/mesh/message` then `mesh_bridge.relay` | Signed packet to the hub; the hub logs it, then `instruct()`s the recipient in **another fresh process**. No direct channel. |
| Authentication | `nexxus_governance.validate_nexxus_command` -> `axis_gate.core.check_packet` | HMAC-SHA256 over sorted-keys JSON, allowed origin, finite timestamp within 60 s, single-use signature (in-memory replay cache, bounded), decision log rate-limited. |
| Second path | `/api/bus/*` (orchestrator bus) | register / order / poll / accept with a hash-chained ledger. A separate system from the mesh. |

## 2. Side-by-side with the standard multi-agent paradigms

| Dimension | NEXXUS mesh | Root orchestrator + isolated subagents (typical) | Assessment |
|---|---|---|---|
| Routing | By name, fixed list of 21, no model in the loop | Orchestrator (an LLM) decides who gets what | **NEXXUS is stronger on determinism**: routing never varies. |
| Isolation | One OS process per call; nothing shared | Separate context windows; results come back as a summary | Equivalent in spirit; NEXXUS isolation is stricter (OS-level). |
| Dispatch model | Stateless request/response (like a tool call) | Stateless tool dispatch | Same pattern. Cost: cold start each call (see section 3). |
| Message passing | Signed HTTP packet, hub-mediated, one hop to a *fresh* process | Parent passes a task, child returns a result | The recipient's live process never sees a relayed message, so relayed messages cannot build up state. |
| Input validation | Signature + freshness + replay; **no schema** for bodies/results (`_clean_metrics` is the only sanitiser) | JSON-schema validated tool inputs | **Gap.** |
| Result semantics | `instruct()` returns `status:"success"` whenever the process ran, even if the engine returned `{"error": ...}` (measured: relay to `axis-core` returned `status success` with `result {"error":"unknown instruction 'message'"}`) | Tool results carry an explicit error flag the orchestrator acts on | **Gap: an "idle true".** |
| State verification | Heartbeat age <= max(3 x interval, 3 s), in memory, lost on hub restart | Parent verifies returned results; transcripts persist | Works (measured flip to stale 24 s after closing a window); not durable. |
| Identity | One shared secret; origin is always `NEXXUS_EXECUTOR` | Per-agent scoped permissions | **Gap: any holder of the secret can sign as any engine.** |
| Failure handling | Timeout kills the process; no retry, back-off or circuit breaker at the hub | Parent retries, re-plans, or decomposes | **Gap** (the daemon engine has the circuit-breaker pattern for services; the mesh does not). |
| Observability | `/api/mesh/telemetry`, diagnostic report, gate ring; per-call `ms` is returned but not aggregated | Per-agent traces | Partial. |
| Capability | **0 utilities declared across all 21 engines** (measured via `/api/mesh/utilities`) | Subagents exist to do work | **The biggest finding: see section 4.** |

## 3. Bottlenecks and latency vectors (measured)

1. **`localhost` costs ~2,030 ms per new connection on this PC; `127.0.0.1` costs ~4 ms** (500x). `nexxus_env.bat` sets `NEXXUS_MESH_URL=http://localhost:8000`, so every engine's signed heartbeat, `get_peers`,
   `send_to_nexxus`, and the health probe pay it. The same default appears for Ollama (`localhost:11434` in `nexxus_talks.query_local_llama`, `llm_router.OLLAMA_URL`, `python_server.py`) and for the gateway
   (`localhost:8080` in `mesh_bridge`/`axis_bridge`). This single setting is the largest latency vector found, and it is a one-word change.
2. **Cold process per call.** Interpreter start ~75-90 ms; a no-op `--mesh` call ~295 ms *(under load)*. Every `instruct`, `call` and `relay` pays this. The peak-memory sampler also polls every 5 ms for the life of each call.
3. **Health probe was 2,426 ms per engine, now 390 ms** *(under load)*: my first health check used `localhost` (item 1). Fixed in section 5.
4. **Message log** (`post_message`): read, append and rewrite the whole file (cap 500) under one lock, and `instruct()` logs again, so a relayed message causes two rewrites. Fine at today's volume (1.1 KB file); latent at scale.
5. **Heartbeats are not a bottleneck**: 21 engines every ~10 s is ~2 requests/s; a signed heartbeat round trip measured 6.9 ms *(under load)*.
6. **Hub restart blanks liveness and the replay cache** (`_LIVE`, `_LAST`, `_replay` are in memory). The dashboard is empty until the next beats (<= ~10 s), and a packet captured in the last 60 s could be replayed after a restart (bounded by `max_age`).

## 4. The "remaining 20%": what it was and what is really left

The 80% figure was a **floor**: the diagnostic does not score stage 4 (answers a probe) unless the probe is run. With `--probe` the score is 100% (21/21 answered). That number measures *presence*: found, opted in,
parses, answers a probe, heartbeat. It does **not** measure capability, and the real gaps are:

| # | Gap | Evidence |
|---|---|---|
| 1 | Engines declare no work | 21 engines in the utilities cache, 0 utilities total |
| 2 | Health content was ignored | `responds = probe_result["status"] == "found"`; an engine answering `ok:false` still scored a pass (**fixed**, section 5) |
| 3 | Relayed messages have no standard handler | the template's `mesh_handle` returns `unknown instruction` for anything but `status`; the hub still reports success |
| 4 | "Exchanged messages" is judged from log presence | it never checks that the recipient *handled* the message |
| 5 | No payload/result schema | free-form JSON in both directions |
| 6 | Shared-secret identity | origin is constant, so engine identity inside the packet is self-asserted |

## 5. Changes made in this pass (additive, no working path altered)

- `mesh_bridge.probe_engine`: an engine that answers `ok:false` is now `unhealthy` with the failed checks named; engines that never said `ok` (legacy shapes) behave exactly as before. Tested in `test_engine_health_bt.py` (needs a server restart to take effect in the live hub).
- Engine `mesh.py` health check: uses `127.0.0.1` for its hub check (2,426 ms -> 390 ms per probe).
- Earlier in the same effort: real health checks in all engines, a plain-words chat message when Ollama is down, and the Bluetooth/tunnel messages.

## 5b. Applied after review (P0 and P1 items 2 to 6, 2026-10-13)

| Item | What changed | Where | Proof |
|---|---|---|---|
| P0 localhost | Outgoing defaults now `127.0.0.1` (147 lines, 62 files): `NEXXUS_MESH_URL` in `nexxus_env.bat`, every `mesh.py` / `live_status.py` / `nexxus_link.py`, `orchestrator_client`, `register_orchestrators`, `portal_chat`, `axis_bridge`, the Ollama defaults in `python_server`, `llm_router`, `nexxus_talks`. User-facing links are left as `localhost`. | many | `test_mesh_hardening.py::P0Localhost` |
| 2 honest envelope | `mesh_bridge.instruct`: an engine that answers `{"error": ...}` is `status:"error"` (result kept); `ok:true` wins over a stray error key; other shapes unchanged. | `mesh_bridge.py` | tested |
| 3 handshake | Every engine answers `ping` and `message` (`ok:true`, meaning *received*, not *acted on*). `relay` returns `handshake {delivered, acknowledged}`, logs an `ack`, counts per pair (`/api/mesh/telemetry` -> `handshakes`). The diagnostic gains "Handled a relayed message". | 23 `mesh.py`, `mesh_bridge.py`, `mesh_diagnostic.py` | tested, and 21 engines answer in a subprocess |
| 4 strict heartbeat | A present-but-invalid `interval` / `state` / `metrics` is a 400 `invalid heartbeat: ...`; a missing one takes the documented default (10 s, "running"). | `mesh_bridge.check_heartbeat`, route | tested |
| 5 per-engine keys | `engine_key = HMAC(secret, "nexxus-engine-key/1:" + name)`; engines sign with `sign_as_engine` (origin `ENGINE:<name>`); the hub derives the key from the engine the packet claims, so A cannot sign as B. Legacy shared-key packets still work until `NEXXUS_REQUIRE_ENGINE_KEYS=1`. An older governance copy falls back to the shared key. | `nexxus_governance.py`, `mesh.py` / `live_status.py`, 3 routes | tested incl. impersonation |
| 5 replay floor | `axis_gate.check_packet(..., min_ts=)`; engine packets older than the hub's start are refused, closing the "replay once after a restart" window without persisting the cache. | `axis_gate/core.py`, governance | tested; gate suite 131/131 |
| 6 durable liveness | Last heartbeat per engine saved (batched every 5 s, atomic) to `mesh_liveness.json` and loaded at start: after a hub restart each engine shows its real age (stale), not blank. Future timestamps and unknown names are ignored. | `mesh_bridge.py` | tested |

Rollout (done 2026-10-13): hub restarted at 03:17 and engines restarted at 03:31 (all 42 processes started after the new code); strict mode proven on a throwaway hub (an engine signing with its own key was accepted, a shared-key packet got 401); probe 21/21; ring handshake 21/21 acknowledged by the right engine. `NEXXUS_REQUIRE_ENGINE_KEYS=1` is now in `nexxus_env.bat` and takes effect at the next hub restart (`restart_nexxus.bat`). To revert, delete that line and restart the hub. Test residue that an earlier version of `test_mesh_hardening.py` wrote into the real `mesh_messages.json` (28 stubbed rows, ids 8 to 35) was removed with a backup in `logs\`; the test now uses a temp log.
## 6. Recommended hardening, in priority order (P0 and P1 items 2 to 6 are now applied: see 5b; P2 and item 1 detail remain as recommendations)

**P0, one-line and measurable**
1. Set `NEXXUS_MESH_URL=http://127.0.0.1:8000` in `nexxus_env.bat`, and change the `localhost` defaults in the `mesh.py` template (`send_to_nexxus`, `get_peers`, `send_heartbeat`), `llm_router.OLLAMA_URL`, `nexxus_talks.query_local_llama` and the gateway calls to `127.0.0.1`.
   Acceptance: heartbeat/ping round trip from ~2,030 ms to ~4 ms; chat gains ~2 s per turn back.

**P1, closes the "idle true" and handshake gaps**
2. **Honest result envelope**: in `mesh_bridge.instruct` / `call_utility`, if the engine's result is a dict containing `error`, return `status:"error"`. Acceptance: the `axis-vision -> axis-core` note test returns an error until a handler exists.
3. **Standard `ping` instruction** in the template (`{"ok": true, "engine": ENGINE_NAME, "ts": ...}`) so every engine can answer a relay; the diagnostic's "exchanged messages" check then requires a *handled* round trip in the last N minutes, not just a log entry. This is the guaranteed inter-engine telemetry handshake.
4. **Strict heartbeat validation** in `record_heartbeat`: `interval` numeric in range (reject, not silently default to 10), `state` from a fixed set, metrics typed. Return 400 on violation.
5. **Per-engine derived keys**: `key_e = HMAC(secret, "engine:" + name)`; the hub verifies a packet with the key for the engine it claims. Engine A can then no longer heartbeat or message as engine B. Keep the shared-key path for a deprecation window.
6. **Durable liveness**: persist each engine's last-heartbeat time (batched, atomic) and the last 2 minutes of replay signatures so a hub restart does not blank the dashboard or reopen a replay window.

**P2, structural**
7. **Per-engine circuit breaker and retry** around `_run_engine` callers (reuse the daemon engine's pattern): open after N failures in a window, half-open probe, surfaced in telemetry.
8. **Capability registry**: require each engine to declare at least one utility, or an explicit reason it declares none; add a diagnostic stage "declares work" so LIVE can be tied to capability.
9. **Warm-worker dispatch** (optional): a local socket on the running engine so the hub calls the live process (about -300 ms per call, and state can persist), with the cold spawn kept as the fallback.
10. **Message log as append-only JSONL with periodic compaction** and the same hash chain the orchestrator bus ledger uses; aggregate per-call `ms` into p50/p95 in telemetry.
11. **Consolidate the two communication paths** (mesh and `/api/bus/*`) or document which is canonical for which traffic.

## 7. What not to change

The deterministic routing, the gate's HMAC + freshness + single-use checks, process isolation per call, the admin-token gating of anything that runs engine code, and the heartbeat design all work and are strengths relative to LLM-routed orchestration. The upgrades above add checks around them; they do not replace them.

