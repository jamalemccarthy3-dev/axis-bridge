# Factory: dashboard types, generators and the lab

The **Dashboard Types** panel (Dashboards room) has a slider on the right. Each stop is a kind of dashboard, with its own form, its own instances and its own tests. Nothing is pre-filled:
the forms come from each type's contract (`/api/factory/types`), and what you build is stored in `factory_data/` (git-ignored).

| Type | Generator | What you get |
|---|---|---|
| Micro-company | `micro_company.py` | Bots that run named tasks on a schedule and hand each result to the next bot (health check, creation job, video make, publish stage, channel check, owner-allowlisted webhook, report). Hourly caps, a hash-chained run ledger and a kill switch. |
| Platform factory | `factory_platform.py` | A branded multi-page site or storefront from your brand, copy and Creations-hub assets. Escaped, no external files, orders and messages go to a local inbox (`/api/factory/<id>/inbox`). No payment is taken. |
| Spatial environment | `factory_env.py` + `factory_env_physics.js` | A playable 3D page: staged objects, lights, gravity and collisions (own physics, same file in browser and Node), first-person WASD + mouse. Image panels take a texture from the Creations hub. |
| Publishing pipeline | `factory_hub.pipeline_company` + `video_maker.py` | Topic and brief in, a real mp4 text-card video out, filed in the Creations hub and staged (private) in the publishing queue. You approve and dispatch. |
| Custom | `factory_types.py` | Your own name and fields. Optionally built with one of the generators above (it must include that generator's required fields). Cannot change a built-in type or see another type's instances. |

Every generator checks its own output before reporting "built" (pages parse, links and assets resolve, no external URLs, scene reads back identical, scripts pass `node --check`, textures match their source, videos decode).

## Image to 3D
In the Spatial environment view: give a web address and a name. `image_ingest.py` fetches that exact image (https only; every address it resolves to must be public; the connection goes to the
checked address; max 3 redirects, 8 MB, 15 s; png/jpeg/gif/webp decided by the file's own bytes; svg refused; scaled to 2048 px if larger), `/api/factory/image-to-3d` files it in the
Creations hub, binds it as the texture of a panel (proportions from the image), builds and checks the scene, and returns each step with its timing. The result opens in the grid below.

## Send button
Send (Enter) is immediate. The caret beside it opens: **Send now**, **Queue for later** (Alt+Enter: kept in this browser, up to 50, sent one at a time in order by "Send queue now", waiting for a
free input slot between each), and **Dry run** (Ctrl+Enter: sends nothing; shows the address, size, SHA-256 and the live state of the two-slot input queue).

## Lab
Every built-in type has a Live demo (a labelled instance built with the real engine) and Stress (light/heavy): generated load on the real engine with CPU/memory sampled by psutil. Results go
to `factory_data/lab/telemetry.jsonl` and show in the panel. Stress measures the machinery, not GPU frame rate (only a browser on your screen can report that).

## What it will not do
- Place calls or send SMS/telemarketing: a bot whose task names such an action is refused with the reason. Outbound contact with people is yours, or goes to a service you are licensed and have consent for through an allow-listed webhook.
- Create a YouTube channel (the API cannot) or upload without your approval: staging is automatic, approval and dispatch are yours (`publish_queue.py`, dry run unless `NEXXUS_PUBLISH_LIVE=1`).

Tests: `test_factory.py`, `test_image_ingest.py`, `test_publish_queue.py` (all in `verify_all.py`).

## 3D staging view (edit a picture, then sync it back)
Click the thumbnail of any picture (Creations list, drawer or detail, or the Image-to-3D result) and the page switches into the staging view: the picture as an object you can orbit (drag, pinch or
scroll), with a toolkit on the side. Every tool sends what you marked to `/api/stage/<session>/apply`; the server edits a **private working copy** (the original is never touched) and the picture
updates in place. Undo, Reset and an edit log are always there. **Finalize and sync to vault** files the result as a new linked version in the Creations hub (the depth map too, if you made one).

| Tool | What it does (and what it is not) |
|---|---|
| Trim the border | Measures the border colour (or transparency) from the image's own edge pixels and crops to everything that differs. |
| Crop box | The rectangle you draw, exactly. |
| Isolate subject | Magic wand: tap a region of similar colour, then remove it (tap the background) or keep it (tap the subject); tolerance and edge feather. |
| Background from edges | Clears every region of border-like colour touching the edge. Colour-based, not a learned model: clean on plain or smooth backgrounds, use the wand or lasso on busy ones. The result says how much was cleared. |
| Lasso | A polygon you tap out: keep or remove inside, feathered. |
| Alpha mask | Feather, hard threshold, invert, or keep only the biggest piece (drop specks). |
| Depth | A depth map from the silhouette (a dome; best after isolation) or from brightness (a relief), shown as real displaced geometry. This is not a learned depth estimate, and the panel says so. |

Code: `image_tools.py` (the edits), `stage_sessions.py` (working copies), routes in `python_server.py`, view in `babylon_preview.html`. Test: `test_staging.py`.

## Remote access (Tailscale, phone)
`NEXXUS_BIND` (set to `loopback,tailscale` by `restart_nexxus.bat`) makes the server listen on this machine's Tailscale address(es) as well as loopback. It never listens on all interfaces; the
Wi-Fi/LAN address is only added if you put `lan` in it. Only loopback and Tailscale peers are served (a 403 otherwise; `NEXXUS_ALLOW_LAN=1` also admits the private LAN). Changes still need the
admin token. On the phone, open `http://<this PC's Tailscale IP>:8000/` (`tailscale ip -4`). To turn remote access off: `set NEXXUS_BIND=loopback`.
- **Heartbeat and reconnect** (`api/ping`, `api/events`): a live stream with a heartbeat every 15 s plus a ping every 10 s. If neither is heard for 25 s the stream is reopened with growing waits
  (1 s to 30 s); going back online, a network change (Wi-Fi to cellular) or returning to the page reconnects at once. After an outage or a host restart everything is refreshed. A pill shows only
  while the link is not healthy.
- **Shared state:** the command queue lives on the host (`api/dispatch-queue`, admin token), so phone and computer see one queue and exactly one device gets each item; without the token or while
  offline it is kept on the device and joins the host queue when possible. Creations, notifications, the input queue, tool log, publishing and factory changes arrive as "something changed" events
  (counters only, never content) and each device refreshes from the normal routes.
- **Phone layout:** at 820 px and below the page uses a phone layout (sidebar as a drawer, full-width command box, 44 px targets, 16 px inputs so iOS does not zoom, landscape rules). The staging view
  stacks the 3D viewport over the toolkit; generated 3D pages get a thumb stick, look-drag and a jump button. Everything uses pointer events, so mouse, touch and pen share one path.
Code: `net_bind.py`; routes in `python_server.py`; `babylon_preview.html`. Test: `test_remote.py`.

## Opportunity Desk (grants and contracts, honestly)
Dashboards room, below Dashboard Types. `opportunity_desk.py` finds real opportunities (the official Grants.gov search API, read-only and rate limited, or one you add by hand), checks each against
your **entity vault** (eligibility from the funder's applicant types; anything it cannot decide is "review" with the reason), turns what is missing into a **questionnaire**, and after **your
sign-off** compiles a packet: cover letter, organisation profile, narrative, budget, key personnel, past performance, attestations checklist, submission notes, one printable HTML, and a manifest
with SHA-256 hashes. The packet describes the organisation exactly as the vault records it (a one-person practice is described as one). A **claims check** blocks the packet if any text claims more
staff than the vault lists, more years than the organisation has existed, or a scale the vault does not record (offices, global network, Fortune 500 clients). It never submits anything and never
stores an EIN, SSN, bank or card number. A sign-off goes stale if anything changes afterwards. Everything is written to a hash-chained ledger. Data lives in `opportunity_data/` (git-ignored).
Test: `test_opportunity_desk.py` (a live Grants.gov check runs with `NEXXUS_LIVE_NET=1`).

## Locks for remote use
From another device (a Tailscale peer, or a request the tunnel proxy forwarded) anything that changes something needs the admin token, except the chat and screen plumbing listed in `_REMOTE_OPEN`
in `python_server.py`; from this computer's own page nothing changes. A change request that carries a foreign `Origin` header (another web page) is refused. Once the token is unlocked the page
attaches it to every call. Checked by `test_gauntlet.py` (every mutating route, from a Tailscale address and from a foreign origin).

## Gauntlet
`test_gauntlet.py` is the pressure test (concurrent fetches, parallel renders, Tailscale latency and dropped connections, red team across every mutating route, 5000 garbage configs, mid-pipeline
corruption, 6 MB body floods, runaway bots and the kill switch, rule pressure, and a control-path audit of every button). It prints a measured report. It tests what exists: AI video, AI
presenters and ad-network posting are not built, and the language model itself is not part of it.

## Campaign Kit (marketing, honestly)
Dashboards room. For ONE real business you enter facts (what it does, who it is for, the offer, real differentiators and proof points, a call to action, a sender name and a postal address). From
those, and only those, `campaign_kit.py` builds: video scripts (15 s, 30 s, 90 s) that fit their running time at a speakable pace; ad copy that fits each channel's limits (Google search 30/90,
Meta 40/125, LinkedIn 70/150, TikTok 100, native 60/150); a 5-email sequence (every email carries your sender name, postal address and an unsubscribe line, or none is produced); branded graphics in
7 sizes (WCAG contrast checked, text fitted into measured boxes so nothing overlaps); and a self-contained responsive landing page. Copy is rejected if it contains a number, a quoted statement or a
claim ("guaranteed", "risk-free", "#1", ...) that is not in your profile. A local model may rewrite the copy; its text goes through the same checks and falls back to the template if it fails them.
`campaign_media.py` makes a narrated video: real synthetic narration from the Windows voices installed here (named in the report; David and Zira on this machine, standard quality), a synthesised
music bed ducked under the voice with a cue on the call to action, an end card with a disclosure line; the file is decoded back and checked (video and audio streams, length within the format).
`campaign_queue.py` is the approval gate: staged -> approved (one item at a time, optional schedule) -> exported. Exporting writes a ready-to-post package (copy, hashed files, schedule, the exact
steps in that platform's own tool, an AI-content disclosure). **Nothing is posted**: the platforms' publishing APIs need an app registration and the account owner's authorisation. Data in
`campaign_data/` (git-ignored). Tests: `test_campaign_kit.py`, `test_campaign_media.py`, `test_campaign_queue.py`, `test_campaign_routes.py`.
Not built: photoreal AI footage or AI presenters (they need a text-to-video / voice service and a licence), undisclosed synthetic endorsements, bot-driven posting.

## Document Factory (proposals, statements of work, contracts, invoices)
`document_factory.py` (nexxus folder). `DocumentFactory.create_doc("proposal" | "sow" | "contract" | "legal" | "invoice" | "billing", payload)` returns the document as markdown, escaped self-contained HTML and JSON, with
warnings. It is also reachable in chat ("write me an invoice ...", routed by `nexxus_talks.py`; only a real request to write one matches, so talking about a contract is not hijacked): facts come as lines like
`field: value` or one JSON object, and anything missing comes back as a question.
- Nothing is invented. Parties, amounts, dates, scope and jurisdiction come from you. Money is exact (Decimal), every total is recomputed, a payment schedule that does not add up to the fee is refused (percentages are
  rounded so the last instalment makes the sum exact).
- A contract needs its **governing law from you**, is stamped "template for review, not legal advice", carries `requires_legal_review`, and lists which standard clauses and defaults were applied. An SOW needs acceptance
  criteria for every deliverable. An invoice shows payment instructions only if you gave them.
- Files are written atomically with SHA-256s to `DOC_FACTORY_OUTPUT_DIR` (master_config.py: `D:\NEXXUS\data\documents`). If that drive is not on the machine they go to `nexxus_data/documents` and the reply says so;
  `NEXXUS_DOC_DIR` overrides both (`nexxus_paths.py` reads master_config as constants and never imports it).
Test: `test_document_factory.py`.

## Core drive (the dashboard's own mount)
`core_drive.py`: `NEXXUS_HOME` (D:\NEXXUS) is the dashboard's core memory. The dashboard creates its layout (`data/documents, state, logs, archives, sketches, campaigns, modules, builds, ...`) when the server starts, and
what is built through it is filed in with `sync()` (atomic, SHA-256, recorded in a hash-chained `mount_index.jsonl`; names cannot leave the mount). `GET /api/core/drive` reports the layout and the index. This PC has no
D: drive, so the mount is `nexxus_data/` here, and the status says that in words; plugging a D: in changes nothing else.

## Daemon Engine
`daemon_engine.py` (nexxus folder), settings in `master_config.py` (`DAEMON_*`, read as constants). Five modules:
- **Process Supervisor**: boot in dependency order (Ollama on 11434, then the dashboard, then the `nexxus_talks` library check, optional Scrapy jobs), readiness by port and URL, health loop, restarts with back-off and a
  circuit breaker (a service that keeps dying is reported, not restarted forever). A service that is already running is **adopted**, never started twice; a process it did not start is stopped only by a restart you ask for,
  and only after its command line is checked to be that service. The dashboard defaults to port **8000**: 8080 is the module gateway.
- **Atomic State Guard**: `business_state.json`, `ledger.json`, `crm_vault.json` are written tmp, fsync, `os.replace`, with a `.bak`, a lock per file, and recovery (a corrupt file is set aside, not overwritten). It never creates
  a state file you have not written.
- **Health Telemetry**: `system_health.json` with a green / yellow / red indicator per service, Ollama models, CPU / memory / disk, state files and logs (`GET /api/daemon/health`).
- **Log Rotator**: over the size or age limit goes gzipped into the archive folder, verified by reading it back, then cut. Ledgers and hash chains are never rotated.
- **Command bridge**: `python daemon_engine.py run | status | health | rotate [--dry-run] | start|stop|restart <service> | shutdown`, or in chat ("how are the services", "rotate the logs", "restart ollama" which needs a
  confirm reply and the running daemon). `POST /api/daemon/command` needs the admin token.
Hooking it in: edit `DAEMON_SERVICES` in master_config.py (a service is a dict: name, kind daemon|module|job, cmd as a list, port, ready URL, depends). `NEXXUS_DAEMON_SERVICES_FILE` points at an alternative JSON table.
Test: `test_daemon_engine.py` (real child processes and a real standalone daemon).

## Sketch Mode
Mode selector > Sketch. A drawing board (domain, working hypothesis, the thread, the thesis), a four-stage rail (Domain, Working hypothesis, Deep-dive, Final thesis) and side-rail **suggestion pills** that change with the
stage and the sketch. You move between stages when you choose (a pill, or words like "draft the thesis", "go deeper", "back to the hypothesis"); nothing nags: closing questions in a model reply are stripped before you
see them, and no pill offers to finish. Nothing is built while sketching. **Build** packages the thesis (blueprint.json / .md / build_order.txt / MANIFEST with hashes), files it in the core drive (`builds/`), switches to the
build room you picked and sends the order; that room's own staging and approval still apply. Your words and the model's analysis are kept apart, and the model's are labelled unverified. Code: `sketch_mode.py`,
routes `/api/sketch*`. Test: `test_sketch_mode.py`.

## Adaptation Engine (SLAE) and what "immunity" means
`sl_adaptive_core.py` (nexxus folder), `SLAE_CONFIG` in master_config.py. `capture_and_convert(error_signature, source_node, stack_trace, context)` records a real failure (timestamped, secrets redacted, hash-chained
`failure_history.jsonl`) and synthesizes one preventative rule per signature in `adaptation_registry.json` (vault `D:/vault/failures/`, or `nexxus_data/vault/failures` when there is no D:). A rule is data, never executed
code. When the signature says what to check (a missing key, a missing path, a refused local port) the rule is **enforceable** and `preflight()` / `guarded()` stop the next run before it starts; otherwise it is
**detect-only** and says so. `total_resolved` means converted into an active rule, **not** that the cause is fixed: `recurrences_after_rule` is the honest measure. `auto_remediation` means rules are activated
automatically; it never restarts services or edits code. `nexxus_talks.generate_response` reports its failures and timings into it; the loop (default every 30 s) folds feedback into per-node stats and captures a service
the daemon turns red. `get_system_immunity_stats()` / `GET /api/slae/stats` feed the dashboard; "immunity" in chat reports it. Test: `test_slae.py`.

## AXIS-CLOUD vault container
`axis-cloud/axis_vault_container.py`, settings `AXIS_VAULT_CONFIG` (axis-cloud `master_config.py`; with no master_config beside the file it uses the same defaults). Drop the one file into any folder and run it: it
provisions `AXIS_SECURE_VAULT/` and `vault_activity.log` there, and mirrors every file with `sync_file()`: copy to a temp file, fsync, require the source did not change during the copy (hash before = bytes written =
hash after), read it back, then `os.replace`. A changed file keeps its earlier version in `_versions/`; nothing is ever deleted from the vault; paths are confined to the folder (symlinks and cloud placeholders refused);
big files are skipped and reported. `mirror_to` adds more existing folders. Terminal lines `[AXIS-VAULT] ... SYNC_OK / SYNC_FAILED / VERIFY_OK / HEALTH green|yellow|red` and `vault_status.json` carry the telemetry.
It is isolation, verified copies and tamper evidence: it is **not encryption or access control**, and it does not claim to be impenetrable. Test: `test_axis_vault_container.py`.

## Engine health, chat fail-safe, Bluetooth and Share (A-grade pass, 2026-10-13)
- **Engine health is measured.** Every engine's `mesh.py` used to answer `{"ok": True}` (the template's TODO). It now runs real checks: its own file parses, it can sign a packet (governance module + secret), and the hub answers; `ok` is false if any fails, and
  it also reports folder writable, free disk and memory. The `status` instruction returns real state and numbers. A one-shot probe has no heartbeat thread, so the dashboard's heartbeat age remains the live-ness signal. Test: `test_engine_health_bt.py`.
  Verified live: `python mesh_diagnostic.py --probe --verbose` (needs `NEXXUS_ADMIN_TOKEN`) answers 21 of 21; a wrong hub address or a missing secret flips an engine's health to false.
- **Chat when Ollama is stopped** says, in plain words and within a second, that the model is not answering and that everything else is still running (no exception text; the detail goes to the server window). Default chat context is now 2048
  (`NEXXUS_CHAT_CTX`) because this PC has 8 GB and the model's memory grows with the context. Test: `test_chat_failsafe.py`.
- **Bluetooth** reports "no usable Bluetooth radio" when Windows has no adapter (this PC currently has none: no Bluetooth devices at all, service stopped) instead of a raw bleak exception, and the panel data shows unavailable until a scan works.
- **Share** explains "Tailscale Serve is not switched on for your tailnet" with the approval link instead of timing out. That is a one-time approval in your Tailscale account.
- Wrong signing secret: the server answers 401 `bad or missing signature`; the engine-side validator prints `SECURITY ALERT: Unauthorized command attempt rejected (bad_signature).`
- Engines are in windows titled `ENGINE <name>`; closing one flips the dashboard to NO HEARTBEAT (the dashboard status goes `stale`) in about 24 seconds. A python process killed inside a window is restarted by the window within seconds.

## The A+ checklist (every new engine, module or dashboard must pass it; the grader's full text is QUALITY_CHECKLIST.md)
`python engine_checklist.py <engine>` (add `--stop-test` to prove isolation and time the dashboard flip; `--all` for the mesh; `--file path --name x` for a new engine not on the roster yet). It writes the raw output to
`logs\engine_checklist_<engine>_<date>.txt`. The nine items and what counts as evidence:
1. **Real health check**: tests what the component depends on (its file parses, it can sign, the hub answers). Healthy is exactly `{"ok": true}`; the failure answer carries the failed checks and a plain reason; `health_detail` carries the numbers.
2. **Failure tested**: hub down, secret missing, governance module missing: exit code 0, plain message, no exception text.
3. **Isolation**: close its window; the other engines keep reporting and the hub keeps answering (`--stop-test`).
4. **Visible state**: the dashboard flips it from LIVE to stale within 3 x heartbeat + 5 s = 35 s (measured 24.1 s, 28.5 s, 24.1 s on 2026-10-13).
5. **Handles messages**: `message` is received and kept in an inbox on disk (the hub starts a fresh process per call, so memory would not survive), `ping` answers, your own `on_message(sender, payload)` hook runs if defined and a crashing hook is reported without stopping the engine, unknown instructions are refused with a reason, and a message relayed through the hub is acknowledged.
6. **No leaks**: responses are scanned for paths, tracebacks, keys and the secret; error text is scrubbed; the secret comes from the environment only.
7. **Landed on a dashboard**: on the hub's roster, shown by the Boiler Room overview, AND `GET /api/dashboards/audit` is ok with no orphans. Every registered bot / profile / vault item must be nested on a dashboard (`NEXXUS Operations` holds the five bots as of 2026-10-13; a new bot is an orphan, and fails this item, until it is nested via `/api/dashboards/<hub>/nest`).
8. **Evidence on file**: a test, a dated raw log, and a commit. While commits are on hold this reports BLOCKED, never PASS.
9. **Tests leave nothing behind**: before and after the run the engine folder is unchanged, `logs\` has no new files except the raw log, and the hub's message log has no new rows (the relay check's own rows are removed again). Tests that talk to an engine set `NEXXUS_ENGINE_INBOX` to a temp file.
Templates for a new engine: `nexxus\engine_snippet_nexxus_governance.py`, `engine_snippet_live_status.py`, `engine_snippet_mesh.py` (concatenate in that order, put `on_message` above the mesh snippet). Tests: `nexxus\test_engine_messages.py` (the grader's, unmodified), `test_engine_health_bt.py`, `test_mesh_hardening.py`.
