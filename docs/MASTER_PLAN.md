# Platform master plan: what exists, what is next, what needs a decision

This page maps every part of the master specification to the software as it stands. **Built** means it works in this repository and has tests. **Partial** means a real part exists. **Needs network** means it cannot exist on one computer: it needs a hosted server, accounts and moderation. **Needs payments** means it needs a payment provider that can settle funds. **Decision** means the spec conflicts with something else and the owner should choose. Nothing is marked built unless it is.

## 1. Core architecture and status

| Spec | Status |
|---|---|
| Free NEXXUS core, open repository | **Built.** Public repo, free to run. |
| "100% live and in production" | The software runs and is tested (`python verify_all.py`). Whether it is "in production" for customers depends on deploying the hosted pieces (billing Worker, telemetry relay) that need your accounts. Public copy should say what is true on the day it is published. |
| Physical translation bus | **Owner-described.** It is not part of the tested features listed in this repository's docs. Document it from your own bus code and tests before it is claimed publicly. |

## 2. Dual funnel (public front end vs subscriber back end)

| Spec | Status |
|---|---|
| Subscriber back end (academy, workspaces, vault, feeds) | **Built locally.** Beta is open; billing is wired and dormant ([BILLING.md](BILLING.md)). The "exclusive portal where members log in" needs accounts: **needs network**. |
| Public storefront for outside buyers | **Partial.** The static export (`marketplace_export.py`) produces a public, no-script storefront with SEO pages; you publish the folder. Live purchase by outside visitors needs a hosted shop and **payments**. |

## 3. Academy and school

| Spec | Status |
|---|---|
| Track A core foundation / Track B practical work | **Built.** Tracks carry `path: A` or `B`. Track A: Operate NEXXUS, The Permanent Foundation (first principles), Industry to Sovereign (translation matrix). Track B: YouTube profile, digital storefront, content pipeline. |
| Permanent Foundation (hooks) + Evolving Pipeline | **Built (foundation) / Partial (evolving).** The Foundation track exists. The Evolving Pipeline is the weekly release mechanism below; the weekly lessons themselves must be authored. |
| Weekly rollout | **Built (mechanism).** A module with `"week": N` stays locked until week N of the learner's academy clock. No future modules are authored yet, so nothing is faked. The 2-week onboarding wave plus 2 new monetization tasks a week is an editorial schedule to author against this mechanism. |
| Translation matrix (RAG, vector DB, agents, fine-tuning, middleware) | **Built** as a Track A lesson. It states the trade-offs honestly (including where hosted wins) instead of "zero leaks" claims. |
| Zero-barrier browsing; bio and quests only to claim Track A | **Built.** Everything is browsable from day one. Company creation needs Track A, the Code of Conduct and a filled-in profile. Quests that need other people (peers, reviews) are shown as not available and are not required, because they could never be completed. |
| Task context lock | **Built.** "Work on this with NEXXUS" locks the conversation to one task; the instruction travels with every message until the task is done or you leave it. It guides the model; it is not a technical wall. |
| Dedicated comments under every lesson | **Needs network** (other people to comment). |
| Strenuous NEXXUS-generated tests as the grading standard | **Partial.** Today badges rest on evidence: NEXXUS checks what it can (profile, posts, vault) and says when a step is self-reported. Generating and running real per-level test suites is a large next build and is not claimed. |
| Badge rationale ("why was this awarded") | **Built.** Every badge shows its evidence. |
| Dual-track merit: technical grade + citizenship points | **Partial.** Technical grade (badges) and a public contributions ledger exist. Citizenship points that depend on peers (feedback, widget sharing, testing others' code) **need network**. |
| Side Quest / constant Train Mode | **Not built.** Needs a defined, token-metered second window and a rule for what "unlimited" means for hosted models. Needs a decision on cost. |
| Open search, truth-filtered video, trend board | **Not built.** Truth filtering a content feed needs human or auditable curation; no video ships until a real, rights-cleared one is added. |

## 4. Workspaces, companies and limits

| Spec | Status |
|---|---|
| 10 dashboards, 10 autonomous bots, 10 profiles per bot | **Decision / Not enforced.** These are limits on things (per-account dashboards and bots) that are not yet per-account objects in the Platform. Also "profiles per bot" must mean the person's own real accounts: NEXXUS will not create accounts or run fake audiences for you. |
| Strict 1-company limit | **Built.** One formal company per person (`teams.MAX_COMPANIES = 1`). Solo workspaces (team / pod) are separate, up to 10. |
| Company creation gate | **Built.** Needs Track A complete. |
| Every team member must participate and prove work | **Needs network.** Teams across accounts do not exist; a workspace has one member. The terms say so in plain words. |
| Terms of Engagement | **Built** (version `alpha-2`, hashed acceptance). Sections 1 and 2 carry a "Today" note for what is and is not true yet. Have a lawyer review before you rely on them. |

## 5. Marketplace

| Spec | Status |
|---|---|
| Vetting gauntlet, free and open tier, SEO, verified ratings | **Built.** See [MARKETPLACE.md](MARKETPLACE.md). |
| $199 as a "publishing gate" | **Decision.** Today $199 is the Lifetime Access Pass; publishing a paid product needs a company, which needs Track A, plus the gauntlet and the 5% agreement. Tying "$199 = permission to publish" would need a tier check in `entitlements.TIERS` (the hook exists). |
| Per-profile vendor stores, main-hub aggregation | **Partial.** Free and paid listings, creator names and a public export exist. Per-profile storefronts need per-account identity: **needs network**. |
| B2B AI workforce exchange (Fiverr-style), client dispatch to leaders | **Needs network and payments.** |
| Netflix-style carousels, App Store cards, skill key codes | **Not built yet.** Pure front-end work over the existing catalog; a good next build. |
| Skill cards with one-click "Equip skill" auto-injection | **Needs a design decision.** Injecting a stranger's endpoints into a live node bypasses the review the marketplace exists to provide. Safer version: equip only vetted, signed packages, with a preview of every permission and a confirm step. |
| GitHub repo bridge for skills | **Partial.** A free listing can link its repository. Live commit sync needs a token and the same confirmation rules as the Discussions sync. |

## 6. Social, messaging, leadership

| Spec | Status |
|---|---|
| Private DM vault, groups, GIFs, voice/video (WebRTC), friends, FYP feed | **Needs network.** Encrypted messaging between accounts needs a server (or a peer relay with signalling), accounts and moderation. The local side keeps private notes private. |
| Leadership roles (Scout, Promoter, Mentor), leader invitation, directory, mentor tagging | **Needs network.** Mentor-ready is the first local step and exists. |
| Mentor revenue share, partner revenue structures, priority dispatch | **Needs payments** and legal terms. |
| Partner Progression Threshold | **Needs network** for the metrics that come from other people; the local half (own badges, contributions) exists. |
| Automated fact-check of submitted videos | **Partial idea.** Logs the NEXXUS container itself wrote can be hashed and checked. Parsing a transcript to prove a claim ran cannot be fully automatic and should not be presented as proof. |
| Cross-platform content (YouTube, TikTok, X) tracking | **Needs the platforms' APIs and accounts.** |

## 7. Onboarding, install, layout

| Spec | Status |
|---|---|
| Friendly first greeting from NEXXUS | **Built.** Warm, optional, pressure-free; shown in Talk to NEXXUS on first use. |
| PWA install prompt | **Built.** Manifest and service worker ship with the dashboard. |
| Desktop auto-run launcher in release bundles | **Check.** `START_NEXXUS.bat` exists in the repository; confirm the release zip includes it before promising "no folder browsing". |
| Responsive safe zone (no text bleeding past the screen) | **Built.** Box-sizing, 95vw limits, wrapping and a fixed header overflow at phone width. |

## 8. Money

| Spec | Status |
|---|---|
| $9.99/month and $199 lifetime | **Built** (Stripe Checkout through a hosted Worker; you supply the keys). |
| $500/month ad slots, creator ad-revenue routing | **Needs payments and a network.** An ad slot is a commercial contract; disclose sponsorships clearly. |
| Founding sponsors | A business and legal arrangement. See [VISION.md](VISION.md); no terms are offered by the software. |
