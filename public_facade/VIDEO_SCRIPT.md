# NEXXUS: 2-minute launch video (script and storyboard)

Private working document (lives with the builder, not in the public repository). Narration: 241 words, about 96 s at 150 wpm; the other ~24 s are music hits, counters and silent beats.
Tagline: **22 engines. One desktop. No GPU. No cloud.**

## 0. Fact sheet: only say what survives a fact-check (measured 2026-10-08)

| On-screen / spoken claim | Measured basis |
|---|---|
| 22 standalone engines | 22 engine folders |
| 21 components live and verified | live mesh telemetry and manifest, 21/21 |
| 250+ utility modules | 278 `*_tool` modules + 31 `*_utility` modules (265 distinct names), each following a main/config/tool pattern |
| 60,000+ lines of code | 61,495 non-blank, non-comment lines in 1,694 code files (53,461 Python); about 5,000 functions and classes |
| 382 checks passing | the master suites' own receipts (96 test files in the workspace) |
| Two-core desktop, no GPU | dual-core i3, 7.9 GB RAM, Intel integrated graphics, Windows 10 |
| 3D from a bundled engine | Babylon.js 9.30.0 bundled; the page loads nothing from the internet (15 requests, all local) |
| Scrapy pipelines | a Scrapy project exists (spiders, pipelines, middlewares, loaders). NOT exercised during this session: film it only after a live run works |

**Dropped on purpose** (each is easy to disprove in the comments): "enterprise-grade", "can't be done locally / industry says impossible", "100% original, found nowhere else", "bulletproof".
Replaced by numbers a skeptic can check. "~100 utilities" became "250+" (the measured count). "21+ engine bridges" became "22 engines, 21 live".

## 1. THE HOOK (0:00 to 0:15)
- **Visual:** Black. A cursor blinks. Cloud-dashboard cards flash and shatter ("Subscription expired", "API rate limit", "Region unavailable"). Hard cut to an ordinary desktop tower, power light on. The NEXXUS dashboard boots. Title card: **Autonomous Automation AI Infrastructure and Orchestrator**.
- **Narration:** "Software used to be something you rented. A subscription. An API key. Someone else's server. NEXXUS is the opposite: an autonomous, multi-engine AI ecosystem that runs entirely on one machine you own."
- **Technical highlight:** SaaS-free, local-first, zero-cloud orchestration; bounded autonomy under human governance.

## 2. THE SCALE AND ARCHITECTURE (0:15 to 0:45)
- **Visual:** Pull back from the desktop into the architecture diagram. The 22 engine folders cascade in as a grid (use the public repository's folder tree). Four counters tick up in sync with the beat: **22 engines, 250+ utility modules, 60,000+ lines, ~5,000 functions**. Engines then converge on a single glowing node, **BRIDGE PORT**, which feeds the core and the dashboard. Overlay: the proof-of-life receipt scrolling green: `COMPONENTS LIVE 21 / 21`. Last frame: a spec plate, "dual-core CPU / 8 GB RAM / integrated graphics".
- **Narration:** "Twenty-two standalone engines. Over two hundred and fifty utility modules. More than sixty thousand lines of code, built to a single design: every engine stands alone, and everything crosses one door, the bridge port. Twenty-one components, live and verified, right now. On a two-core desktop. No GPU. No cloud. No cluster."
- **Technical highlight:** hub-and-spoke integration through a single gateway; per-engine verified heartbeats (21/21 live); process-isolated service modules; single-node, vertically scaled reference build.

## 3. THE CORE CAPABILITIES (0:45 to 1:30), four fast beats

**3a. Local LLM routing (0:45 to 0:58)**
- **Visual:** Dashboard. The mode selector flips *Conversation* to *Build*. Split screen: the local model list swaps (chat model unloads, coding model loads), a build job starts with a live progress console, and the chat box stays responsive as you type.
- **Narration:** "Ask it to talk, and a small chat model answers. Switch to build mode and it swaps in a coding model, locally, and builds in the background while you keep talking."
- **Technical highlight:** mode-based local-model routing through a self-hosted runtime; background job queue with a verification gate. (Do not show model names on screen.)

**3b. Crawl pipelines (0:58 to 1:08)**
- **Visual:** Staging Viewport. Type a target, press Run. Rows stream into named staging categories. A grayed "Save Active Category" button waits for the click, then commits.
- **Narration:** "Need data? Its Scrapy pipelines gather it into a staging area, reviewed by you before anything is committed."
- **Technical highlight:** Scrapy spider/pipeline project feeding a staging area with a manual commit gate. **Only film this after a live run succeeds.**

**3c. AXIS guardrails (1:08 to 1:20)**
- **Visual:** Split terminal and the "axis gate" card. Left: a forged packet is sent and returns `401`; the card's *Blocked* counter ticks up. Right: a sealed file is edited and the next run reads `BLOCKED: modified`. Cut to the tool briefing drawer: risk badge **LOW**, a **BLOCKED** example in red, and the cursor hovering over **Approve & integrate** (human decision).
- **Narration:** "Nothing runs unless it's signed. Forged commands are refused. Tampered code is refused. New capabilities are read, briefed, and added only when a human approves."
- **Technical highlight:** axis gate: signed manifests, single-use verified packets, drift detection; approval-gated, sandboxed capability intake. (Use a throwaway demo instance with test data.)

**3d. The 3D viewport (1:20 to 1:30)**
- **Visual:** A 3D viewport window inside the dashboard, a mesh rotating smoothly. The browser network panel slides in: every request is `localhost`. Lower-third: "Babylon.js 9.30, bundled".
- **Narration:** "Even the interface loads nothing from the internet. The 3D viewport runs from a bundled engine, on integrated graphics."
- **Technical highlight:** Babylon.js 9.30.0 bundled locally and embedded into sandboxed frames; WebGL2 on an integrated GPU; zero external requests at load.

## 4. THE CALL TO ACTION: OBSERVER MODE (1:30 to 2:00)
- **Visual:** The public GitHub repository, scrolling the README: the quote "My time is money. My product is free." as a large heading, the architecture diagram, the receipts block, the folder tree of placeholder files. Three on-screen rules animate in: **OBSERVE. BUILD YOUR OWN. CREDIT THE ORIGINAL (CC BY 4.0).** Then a quick "Skeleton, not source" stamp over the file tree. End card: repository URL, the quote, and small credits: *Built with the open and accessible stack: Gemini, Hugging Face, Llama, Babylon.js.*
- **Narration:** "This repository is observer mode: the full architecture, every boundary, every folder, none of the source. Study it, copy it, build on it, under C-C B-Y four-point-oh: credit the author, link the repo. Build yours with your own local AI, and prove it works. Would rather skip the work? That's the Industrial Build: the architect's fee. My time is money. My product is free. NEXXUS."
- **Technical highlight:** facade/core separation (structure public, implementation private); CC BY 4.0 with mandatory attribution; the builder's assignment; separate commercial Industrial Build agreement.

## 5. Production notes
- **Pacing:** cuts every 1.5 to 3 s; counters and text hit on the beat; no scene longer than 12 s. A low pulse under the hook, a build to a hit at 0:45, a drop to near silence for the guardrail beat, a final lift at 1:30.
- **Look:** near-black UI, one accent color, monospaced captions, green PASS lines for receipts. Keep the dashboard at full screen; never show a desktop with personal taskbar items.
- **A 30-second social cut:** Hook, the counters, the guardrail beat, the end card.
- **Never on screen:** any private file name (wiring, governance, mesh, tunnel, watchdog scripts), `.env` or secrets files, the admin-token prompt, the key panel with any real value, the list of private repositories, local paths or your account's email, model names.
- **Capture checklist (in this order):** (1) full dashboard boot, (2) the mode switch with the model swap, (3) the architecture diagram and counters, (4) the receipts block, (5) the guardrail demo on a throwaway instance, (6) the 3D viewport plus the network panel, (7) a live crawl run (only if it works), (8) the public repository page.
