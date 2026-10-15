# Autonomous Automation AI Infrastructure and Orchestrator: architecture specification (private)

**NEXXUS**, specified.

| In my words | The formal technical equivalent |
|---|---|
| **Autonomous Automation** | **Agentic workflow automation** with bounded autonomy and human-in-the-loop governance |
| **AI Infrastructure** | **Self-hosted, local-first AI infrastructure**: a local model-serving runtime plus a modular multi-engine service platform on a single node |
| **Orchestrator** | **Orchestration layer / control plane**: hub-and-spoke service orchestration through a single gateway, with a policy-enforcement (guardian) layer |
| **The whole system** | **A self-hosted, local-first, multi-engine AI orchestration platform** (SaaS-free, zero-cloud local orchestration) |

Audience: the owner, and anyone who is given the private source. The public, structure-only version of this document is `public_facade` -> `docs/SPECIFICATION.md`.

## 0. Distribution model: infrastructure, not handouts

What is published publicly is the sovereign orchestration framework and **empty utility skeletons**, never the proprietary plug-and-play source. This private specification, the source and the wiring stay private.

| What you get | What you do not get |
|---|---|
| The **sovereign orchestration framework**: layout, boundaries, principles and the specification | Proprietary, plug-and-play engine source code |
| **Empty utility skeletons**: the folder and file structure of every engine, as placeholders | The internal wiring, configuration or data of the reference build |
| A **proven reference**: proof-of-life receipts from a real, local, cloud-free build | A hand-held tutorial, or a script that "just works" |

**The engineering standard.** The architecture is engineered to stand on its own and to run entirely on local hardware with no cloud: the reference build does exactly
that (see the proof-of-life receipts). But a skeleton is only a skeleton. **The implementation, and the execution of it, depend entirely on the builder's capability.**

**Reality check.** This is strictly local-first infrastructure with empty utilities. If you rely on cloud crutches, outsourced APIs, or a hand-held tutorial script,
**this build is not for you.** If you can build, it is the foundation to build on.

## 1. What this system is

A **local-first, SaaS-free, single-machine AI ecosystem**: a core (NEXXUS), a bridge that every component connects through, a set of standalone engines, a dashboard, and
a guardian (the axis gate) that decides what may run or pass. It is designed for **personal sovereignty and high-level autonomous development on one computer**.
It is **not** designed for multi-node cloud scale. Section 5 is the contract about that.

## 2. Components

| Component | Where | Role |
|---|---|---|
| Server / control plane | `python_server.py` | The one HTTP surface: dashboard, chat, jobs, mesh endpoints, tool and key routes, gate telemetry |
| Mesh hub | `mesh_bridge.py`, `mesh_roster.py`, `nexxus_governance.py` | Engine registry, signed heartbeats and messages, utilities cache |
| Module gateway | `axis-ui-interface/_gateway/` | Hostname routing for external modules; a local-only route to NEXXUS |
| axis gate | `axis-ui-interface/project-X/axis_gate/` | Signed manifests, packet verification, drift watch, single-use tickets, decision log |
| Core brain | `silo_vault/nexxus/` | Chat, modes, jobs, build loop, local-model router, tool intake, key box |
| Engines | `silo_vault/axis-*`, `S.A.M.U.E.L.-`, `triad-protocol-module-` | 22 standalone engine folders |
| Dashboard | `silo_vault/render/` | The UI, served by the server; its 3D library is bundled in `render/vendor/` |
| Watchdog / autostart | `nexxus_watchdog.ps1`, `nexxus_autostart.ps1` | Restart what died, start what is missing, at login |

## 3. Integration paths

**An engine joins the mesh.** The bridge publishes a roster of engine files (the server never scans engine folders itself). An engine either is discovered from that roster or
registers itself with a signed packet. From then on it sends signed heartbeats; a heartbeat is accepted only if its signature and timestamp are valid and it has not been used before
(the axis gate decides). "Live" means a recent verified heartbeat; it says nothing about what the engine can do.

**An external module joins the gateway.** Drop a folder with a `module.json` (or a one-line pointer file) into `axis-ui-interface/`; the gateway starts it, routes its hostname,
and, if it declares a NEXXUS block, lets NEXXUS ask it for read-only utilities with packets signed by that module's own key. See `axis-ui-interface/_gateway/MODULES.md`.

**A new capability arrives (tool intake).** Scout or name a GitHub project -> pinned-commit ZIP into `staging_vault` (never executed) -> a briefing computed by reading the code, with the exact
`pip` command and key links it needs -> **your approval** (admin token, bound to the briefing hash) -> `tools_vault` with a gate-signed manifest -> callable immediately through
`/api/tools/call` (owner) or a signed module packet, always inside the sandbox. See `silo_vault/nexxus/TOOL_INGESTION.md`.

**A key reaches a tool.** Left panel (API Key Ingestion) -> single-use gate ticket + structure check -> key box (Windows DPAPI) -> you grant it to one approved tool that has internet
permission -> it arrives only as an environment variable in the sandboxed process, scrubbed from anything the tool returns.

**The dashboard and its assets.** The dashboard is served by the server and loads nothing from the internet at startup. The 3D library (Babylon.js 9.30.0, Apache-2.0) lives in
`render/vendor/` with its checksum in `THIRD_PARTY.md`. Pages shown in isolated frames get the library **embedded inline** (such frames cannot fetch from this server). To update it: replace the
file, record the new version and SHA-256 in `THIRD_PARTY.md`, run `test_dashboard_offline.py`.

**Consultants (optional, off by default).** A silent, LAN-only second opinion, reachable only through the axis gate's single-use clearance. Never shown in the UI or the public telemetry.

## 4. Optional online features (the complete list)

The system runs with all of these off. Each is user-initiated or off by default:

1. **Tool scouting / fetching** from GitHub (`api.github.com`, `codeload.github.com`), only when you ask.
2. **Web search and recon**: the dashboard search box (DuckDuckGo), the chat `search:` command, and the Staging Viewport's scrape/recon pipeline against a target you name. Each runs only when you start it, never at page load.
3. **Remote access tunnel** (Tailscale), only if you set it up.
4. **Consultant network**, LAN only, disabled until you configure a second machine.
5. **`pip install`** of packages a tool needs: you run the command yourself.
6. Links to key-issuing pages are shown as links; nothing is fetched from them.

Everything else, including the dashboard's 3D library and background, is local. `test_dashboard_offline.py` fails if the page ever loads a resource from another host.

## 5. The hardware envelope: what this design can and cannot do

**Contract.** This is a local, sovereign, zero-subscription powerhouse that runs on **single-machine physics**: CPU, RAM and, where present, GPU/VRAM set the ceiling.
It behaves like an "unlimited" plan: very high capability, but once you push past a threshold of **heavy concurrent local generation** you hit the hardware wall. It is built for
absolute personal sovereignty and high-level autonomous development, **not** for infinite multi-node scaling out of the box.
"Zero cost" means no subscription or licence fee. Hardware and electricity are yours.

**Reference machine (measured).** Dual-core Intel i3-3220 (2 cores / 4 threads, 3.3 GHz), 7.9 GB RAM, Intel integrated graphics, **no discrete GPU**, Windows 10, local models run on CPU.
The whole system, 21 mesh components live plus the local models, runs on this. That is the floor, not the ceiling: better hardware raises every limit below.

**Limits built into the code** (all adjustable in source or by environment variable):

| Resource | Limit | What happens at the limit |
|---|---|---|
| Build-time model calls | 1 at a time (a lock; the code notes a 2-core / 8 GB design target) | Further calls wait their turn |
| Background jobs | 2 workers | The rest queue |
| Tool runs | 2 at a time; 30 calls per minute per caller | A "busy" or "too many calls" answer, nothing is dropped silently |
| One tool call | 30 s, 512 MB, 256 KB result | Stopped and reported |
| Model timeouts | 10 to 15 minutes per call | The call fails and the job reports it |
| Model memory | Models stay loaded 10 minutes after use; switching mode swaps models | A swap costs seconds to minutes on CPU |
| Default models | chat: phi4-mini, build: qwen2.5-coder:3b (override with `NEXXUS_CHAT_MODEL`, `NEXXUS_BUILD_MODEL`) | Small models are the practical ceiling on output quality on this class of machine |

**What the wall looks like in practice.** Chat while a build runs works. Several builds, a large model and many engines doing real work at once will queue, slow down, or run out of RAM and
start swapping to disk: latency grows long before anything fails outright.

**How to raise the ceiling (vertical scaling).** More RAM, an SSD, a discrete GPU with enough VRAM, a larger model, higher worker counts. Each is a hardware or settings change on the same machine.

**What is not provided (horizontal scaling).** No cluster scheduler, no shared state across machines, no cross-machine authentication, no failover. Running this across several nodes would be a different
architecture that you would have to design and build. It is also a **single point of failure**: one machine, one disk, one power supply. Back it up.

## 6. Security model limits

- The axis gate is a **tripwire**, not a vault: its signing key and the files it guards live on the same disk. It protects against mistakes, tampering by lesser code, and anything arriving without the key.
- The tool sandbox is a separate process with a Python audit hook and a Windows Job Object. It is a strong guard rail, **not an OS-level boundary**. A tool you grant "start programs" runs outside most of it.
- A key granted to a tool can be sent by that tool to the internet sites it calls. Grant only to tools you trust.
- Windows-specific parts: DPAPI key custody, Job Objects, the PowerShell watchdog.

## 7. Known gaps (honest status)

- About 45% of engine files are very small scaffolds; "live" proves the plumbing, not the capability of each engine.
- The engine-side integration stub is copied into each engine rather than shared (the same typo existed in 14 engines at once).
- A few files saved with a `.py` extension are not Python (HTML/JS snippets, notes). They are listed in the status check.
- Test coverage is strong for the gate, tool intake, keys and jobs; engine behaviour has little.

## 8. The builder's assignment and acknowledgments

The public repository frames adoption as an **assignment**: builders command their own local AI to wire the utilities, starting from a bare-minimum system (one gateway, one engine, one liveness check). See `public_facade` -> `docs/ASSIGNMENT.md`.

**Google and Gemini: the core architectural partner.** A tribute to the free intelligence layer that helped collect the thoughts, structure the engine parameters and co-architect this
system from the ground up. Gemini was a **design-time partner**: nothing in the running system depends on it.

**Hugging Face**, the open hub that makes models, datasets and tooling accessible to everyone. **Llama**, the open-weight models from Meta that make serious local inference possible on ordinary hardware.

Together they are the trifecta of the **open and accessible stack** that made sovereign, local-first infrastructure possible.
Product names and marks belong to their owners; their mention here is gratitude, not endorsement by them.

## 9. Commercial path

The free repository is the blueprint, and the goal is that people **build it themselves**. The **Industrial Build** ($10,000 one time per single-user licence, mandatory digital agreement, optional $1,000/month retainer) is a **service**: the architect's time, engineering and custom architecture packaged as a turnkey setup for those who choose not to build. It is not a charge for files or third-party models. The public summary is the README section "Industrial Build & Enterprise Licensing"; the risks, the pre-sale checklist and the third-party licence findings are in `public_facade/COMMERCIAL_NOTES.md` (private).
