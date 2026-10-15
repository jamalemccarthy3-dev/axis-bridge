# AUDIT.md: how this system was stress-tested

This is the record of an adversarial review of NEXXUS, a local-first, 21-node mesh. It is written for an engineer who wants to know what was attacked, what broke, what was changed
and what was left alone. It is not a score sheet. Every claim here points at a test, a measured number or a log in `logs\`, and where something is not proven it says so.

## 1. Method

- **Adversarial, not confirmatory.** An independent reviewer (an AI model working from the owner's pasted evidence, not from our summaries) was asked to find reasons to fail the build. Our own
  claims were rejected until they came with raw output. Several things we believed were done were sent back (see section 4).
- **Evidence over assertion.** Anything that can be measured was measured on the real machine (8 GB RAM, CPU-only local LLM). The checklist runner writes dated raw output to `logs\`.
- **Guardrail: enhance, never destabilise.** Working core paths were not rewritten. Changes are additive and each has a test that fails without it.
- **Nothing destructive against live data.** Tests run on temp folders. When a test did pollute live data (it happened, see section 4) the residue was removed by id, with a backup first.

## 2. Architecture under review

Two layers with a hard line between them.

| Layer | What it is | What it is not |
|---|---|---|
| **The mesh: 21 headless nodes** | Autonomous background processes. They relay instructions, persist their own state and ingest data. Each sends a signed heartbeat about every 10 s and answers `health`, `ping`, `message` and `instruct`. The hub reaches them through a signed, stateless call. | They have no UI of their own, and are not expected to. |
| **The dashboard: command and aggregation** | Telemetry, the engine cluster rollup, perimeter controls (Hard Lock, Quarantine, breach alerts) and the operator's overrides. | It is not a container of 21 engine widgets. |

**Why the engines are not on the dashboard one by one.** A healthy background engine with no card is not a defect. The audit therefore treats the 21 engines as one rolled-up cluster
(`GET /api/dashboards/audit` -> `engine_cluster`). An engine orphan is a *dead process* (on the roster, heartbeat stale), an *unreferenced folder* (a `mesh.py` the roster does not know) or a
roster entry with no folder. Bots, profiles and vault items are different: they are user-facing objects and must be nested on a dashboard, and the audit still fails on any that are not.

## 3. Hardening applied (each with a test)

| Area | Finding | Change | Evidence |
|---|---|---|---|
| Latency | `localhost` cost ~2,030 ms per new connection on this machine; `127.0.0.1` ~4 ms | All outgoing defaults moved to `127.0.0.1` (147 lines, 62 files) | `test_mesh_hardening.py`; health probe 2,426 ms -> 390 ms |
| Result honesty | The hub reported `success` when an engine answered `{"error": ...}` | Honest envelope: an error answer is `status:"error"`; `ok:true` wins over a stray error key | tested |
| Health | Several engines returned a stub `{"ok": True}` | Real checks of what each engine depends on; a broken dependency reports `ok:false` with a plain message | 21 of 21 probe-verified |
| Identity | One shared secret: any holder could sign as any engine | Per-engine derived keys (`ENGINE:<name>` origin); the hub derives the key from the engine a packet claims. Strict mode refuses the legacy key | impersonation test; strict mode proven on a throwaway hub |
| Replay | Replay cache was memory-only, so a restart reopened a window | Replay floor (`min_ts`) tied to hub start; packets older than the hub are refused | gate suite 131/131 |
| Liveness | A hub restart blanked the dashboard | Durable, batched, atomic liveness file | tested; engines show real age after a restart |
| Handshake | "Exchanged messages" was judged by log presence | Engines acknowledge relayed messages; the hub logs the ack and counts per pair; the diagnostic checks for a *handled* message | ring of 21 acknowledged by the right engines |
| Heartbeat input | Invalid `interval` / `state` / `metrics` were silently defaulted | Present-but-invalid is a 400 | tested |
| Failure behaviour | Local LLM down produced a raw error in chat | Pre-check and a plain-words message; fail-safe kill test | `test_chat_failsafe.py` |
| Isolation | Does one engine dying stop others? | Closed a real engine window: the others stayed live; the closed one showed stale after 24.1 to 28.5 s | measured on 3 engines (see section 5) |

## 4. Engineering wins, and the mistakes that earned them

- **Verification by reading state, not by parsing shell output.** Row counts, file inventories and inbox contents are checked with direct Python file reads (`json` loads and `stat` snapshots taken
  before and after a run) rather than by scraping the text of shell commands. Writes that matter use temp-file-then-`os.replace`, so a reader never sees a half-written file. This is what lets checklist
  item 9 say "this run left nothing behind" and prove it with before/after snapshots of the engine folders, `logs\` and the hub's message log.
- **Tests that pollute are bugs.** Two of our own test runs wrote into live data (28 stubbed rows into the real message log, then 84 inbox messages and 198 checklist rows). They were found by the
  review, removed by id with backups, and the suites now use temp inboxes and logs. Item 9 of the definition of done exists because of this.
- **The reviewer's templates failed his own stronger test.** We kept our templates as the source of truth after a shared-inbox path defect was found, and changed the inbox to one file per engine file.
- **Quarantine release at volume, with a record.** The perimeter holds inert, redacted copies of packets that failed verification; releasing one deletes the copy. For high volume there is now a bulk
  release (`POST /api/perimeter/quarantine/release-all`): admin token, an explicit `confirm`, a count check against what the operator saw (409 if stale), and an `ids` list so anything that arrived during
  an active run stays held. Before anything is deleted, a metadata-only, hash-chained record (`released.jsonl`) is written; if that write fails nothing is deleted, and a removed or edited line is detected.
  Tested on temp folders only (16 perimeter tests).
- **An audit that tells the truth about itself.** It had been failing for a while on 5 orphan bots; the fix was to nest them on a dashboard, not to loosen the audit.

## 5. What is proven, and what is not

| Claim | Status |
|---|---|
| 89 test suites registered in `verify_all.py`; the latest full run (2026-10-14, after the engine-cluster change, Release All and the secret rotation) ended `ALL GREEN`: 89 pass, 0 fail, 0 skipped. Raw output: `logs\verify_all_2026-10-14.txt` | Proven |
| 21 of 21 engines answer a probe; 21 of 21 acknowledge a relayed message | Proven |
| Checklist items 1, 2, 5, 6, 7, 9 for all 21 engines | Proven with raw logs |
| Isolation and stale-time (items 3, 4) | Measured on **3 of 21** engines (`axis-vision`, `axis-link`, `axis-triage`). The engines share one template, so this is a sample, not all 21 |
| Remote access from a phone over mobile data | **Not proven.** Tailscale Serve needs the owner's approval and a real phone test |
| Bluetooth | **Not proven.** The PC has no Bluetooth radio; the code reports that plainly |
| Chat speed | CPU-only local model on ~1.8 GB free RAM: replies are slow regardless of code quality. A hardware limit |
| A clean commit with the evidence | **Blocked** until a credential that appeared in old git history is rotated by the owner |

## 6. Known open items (not hidden)

This build is not "zero technical debt", and claiming that would be false. What remains:

1. Rotate the exposed credential, then commit with the raw logs. History is not rewritten until that is done.
2. The phone test, then Disconnect.
3. Stop tests on the remaining 18 engines.
4. P2 items from `ARCHITECTURE_AUDIT.md`: per-engine circuit breaker and retry, a capability registry (the engines declared no utilities), optional warm-worker dispatch, an append-only message log.
5. No payload or result schema for mesh bodies yet.
6. Commerce layers (flyers, FBA / wholesale logistics, licensing) are not built.

Related: `ARCHITECTURE_AUDIT.md` (measurements and the full hardening list), `QUALITY_CHECKLIST.md` (the nine-point definition of done), `PERIMETER.md`, `FACTORY.md`.
