"""
public_facade/build_facade.py - builds the PUBLIC "structure only" view of the NEXXUS workspace, and refuses to build anything that leaks.

What the public sees:  folders and file NAMES laid out as they are, an architecture overview, and nothing else.
What the public never sees:
  * implementation   every file is replaced by a one-line "withheld" placeholder; no code, config values, docs or comments are copied
  * engine wiring    each engine is shown as an ISOLATED, autonomous folder. Every file or folder inside an engine that exists only to
                     connect it to the bridge (bridge/mesh/governance/heartbeat/master-config/snippet files...) is OMITTED ENTIRELY, names included,
                     so the public cannot tell how, or whether, an engine is wired to anything
  * the consultant network, secrets, key and tool vaults, user data, runtime state, backups, virtualenvs, third-party code
  * private repository history: the output is a brand-new folder with brand-new history (never publish an existing repo with code in it)

    python build_facade.py audit      how coupled is each engine to the bridge today (PRIVATE report, never published)
    python build_facade.py build      build ../../public_facade_out (default: Desktop\\public_facade) and run the leak guard
    python build_facade.py verify     run the leak guard on an existing output folder
Free / local / standard library only. Nothing is uploaded by this script.
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent                                              # axis-bridge
OUT = Path(os.environ.get("NEXXUS_FACADE_OUT") or WORK.parent / "public_facade")
SILO = WORK / "axis-ui-interface" / "project-X" / "silo_vault"

POLICY_FILE = HERE / "facade_policy.json"
try:
    POLICY = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
except (OSError, ValueError):
    POLICY = {}
ENGINE_NOT = {"render", "nexxus"}                               # silo_vault folders that are not engines (dashboard, NEXXUS core)
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules", "instantmesh_env", "bridge_env", "InstantMesh", "nvdiffrast", "dist", "venv", ".venv",
             "site-packages", "vault", "backups", "backup", "logs", "state_backups", "state_logs"}
SHOW_EXT = {".py", ".js", ".html", ".md", ".ps1", ".bat", ".sh", ".txt", ".json", ".c", ".h", ".cpp", ".rs", ".css"}

# a name that exists only to connect something to the bridge -> omitted from every ENGINE folder on the public side
WIRING_NAME = re.compile(r"(bridge|mesh|nexxus|govern|govenor|heartbeat|handshake|live_status|snippet|snippit|engine_snip|deployment_tool|master_|"
                         r"system_pulse|roster|external|diagnostic_|_diagnostic|orders|portal|sovereign|gateway|register|registry)", re.I)
# names that are not published on the BRIDGE and CORE side either: the bridge's own wiring, governance, mesh and operational scripts, and tests (a test name describes a feature)
BRIDGE_HIDE = re.compile(r"(mesh|roster|govern|govenor|heartbeat|handshake|live_status|snippet|snippit|master_|system_pulse|external|orders|bridge_|_bridge|bridge\.|diagnostic|"
                         r"autostart|watchdog|tunnel|bluetooth|peripheral|deployment_tool|ports\.json|start_|stop_|restart_|^test_|_test\.py|test_)", re.I)
# names that must never appear anywhere in the public output (secrets, private subsystems)
_EXTRA = [re.escape(x) for x in POLICY.get("extra_hide_names", [])]
HIDE_NAME = re.compile(r"(secret|token|credential|password|passwd|\.env|nexxus_env|nexxus_admin|restart_nexxus|consult|keybox|gate\.key|\.pem|\.key$|\.db$|\.sqlite|"
                       r"lead_storage|client_configs|creations_vault|staging_vault|tools_vault|session_state|sovereign_archive" + ("|" + "|".join(_EXTRA) if _EXTRA else "") + ")", re.I)
# content markers that show coupling (used by the private audit, and by the leak guard on the OUTPUT)
WIRING_CONTENT = re.compile(r"(bridge_diagnostic|bridge_orders|\bnexxus|NEXXUS|\bmesh|live_status|governance|start_heartbeat|register_engine|localhost|127\.0\.0\.1|:80[0-9][0-9]\b|"
                            r"/api/|\bdeck\.|X-Nexxus|signature|handshake|\bbridge\b)", re.I)
SECRET_CONTENT = re.compile(r"(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|[A-Za-z0-9+/]{40,}={0,2})")
COMMENT = {".py": "#", ".ps1": "#", ".sh": "#", ".bat": "REM", ".js": "//", ".c": "//", ".h": "//", ".cpp": "//", ".rs": "//", ".css": None, ".html": None}
WITHHELD = "Implementation withheld. This file exists in the private source."
PLACEHOLDERS = set()


def placeholder(ext):
    c = COMMENT.get(ext, "#")
    if ext == ".html":
        t = "<!-- %s -->\n" % WITHHELD
    elif ext == ".css":
        t = "/* %s */\n" % WITHHELD
    elif ext == ".json":
        t = '{"withheld": true}\n'
    elif ext in (".md", ".txt"):
        t = "%s\n" % WITHHELD
    else:
        t = "%s %s\n" % (c, WITHHELD)
    PLACEHOLDERS.add(t)
    return t


def engines():
    return sorted(d for d in SILO.iterdir() if d.is_dir() and not d.name.startswith("_backup") and d.name not in ENGINE_NOT and d.name != "__pycache__")


# ------------------------------------------------------------------------------------------------------------- the private audit
def audit():
    rep = {}
    for e in engines():
        own, wiring, mixed, total = [], [], [], 0
        for dp, dn, fn in os.walk(e):
            dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith("_backup")]
            rel_dir = Path(dp).relative_to(e)
            for f in fn:
                if Path(f).suffix.lower() not in SHOW_EXT:
                    continue
                total += 1
                rel = (rel_dir / f).as_posix().lstrip("./")
                parts = Path(rel).parts
                if any(WIRING_NAME.search(p) for p in parts):
                    wiring.append(rel)
                    continue
                try:
                    txt = (Path(dp) / f).read_text(encoding="utf-8", errors="ignore")[:200_000]
                except OSError:
                    txt = ""
                (mixed if WIRING_CONTENT.search(txt) else own).append(rel)
        rep[e.name] = {"files": total, "own_clean": len(own), "own_but_mentions_bridge": len(mixed), "wiring_files": len(wiring), "wiring_examples": wiring[:6], "mixed_examples": mixed[:4]}
    return rep


# ------------------------------------------------------------------------------------------------------------- build
def _walk_entries(root, engine=False, hide=None):
    """Yield (relative path, absolute path) of files to show as placeholders."""
    root = Path(root)
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS and not d.startswith("_backup") and not HIDE_NAME.search(d) and not (engine and WIRING_NAME.search(d)) and not (hide and hide.search(d)))
        rel_dir = Path(dp).relative_to(root)
        for f in sorted(fn):
            if Path(f).suffix.lower() not in SHOW_EXT or HIDE_NAME.search(f) or (engine and WIRING_NAME.search(f)) or (hide and hide.search(f)):
                continue
            yield (rel_dir / f), Path(dp) / f


def build(out=OUT):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        for p in sorted(out.rglob("*"), reverse=True):          # only ever clear a folder this script made
            if p.name == ".git" or ".git" in p.parts:
                continue
            if p.is_file():
                p.unlink()
            else:
                try:
                    p.rmdir()
                except OSError:
                    pass
    out.mkdir(parents=True, exist_ok=True)
    tree, counts = [], {}

    def emit(dest_rel, ext):
        d = out / dest_rel
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(placeholder(ext), encoding="utf-8")

    # engines: isolated, autonomous folders - own structure only
    for e in engines():
        n = 0
        for rel, _ in _walk_entries(e, engine=True):
            emit(Path("engines") / e.name / rel, rel.suffix.lower()); n += 1
        counts[e.name] = n
        (out / "engines" / e.name).mkdir(parents=True, exist_ok=True)
        label = POLICY.get("descriptions", {}).get(e.name)
        (out / "engines" / e.name / "README.md").write_text("# %s\n\n%sA standalone, self-contained engine. Its source is private.\n" % (e.name, ("**%s.** " % label) if label else ""), encoding="utf-8")

    # the bridge side: its own layout only (never the consultant network, secrets or data)
    bridge_roots = [("bridge/server", WORK, False), ("bridge/gateway", WORK / "axis-ui-interface" / "_gateway", True), ("bridge/axis_gate", WORK / "axis-ui-interface" / "project-X" / "axis_gate", True),
                    ("core/nexxus", SILO / "nexxus", True), ("dashboard", SILO / "render", True)]
    for dest, root, recurse in bridge_roots:
        if not root.is_dir():
            continue
        if not recurse:                                          # the workspace root: top-level files only (everything below is covered above or private)
            for f in sorted(root.iterdir()):
                if f.is_file() and f.suffix.lower() in SHOW_EXT and not HIDE_NAME.search(f.name) and not BRIDGE_HIDE.search(f.name) and f.suffix.lower() in (".py", ".ps1", ".bat"):
                    emit(Path(dest) / f.name, f.suffix.lower())
            continue
        for rel, _ in _walk_entries(root, hide=BRIDGE_HIDE):
            emit(Path(dest) / rel, rel.suffix.lower())

    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file() and ".git" not in p.parts)
    desc = POLICY.get("descriptions", {})
    rows = ["| Engine | Label |", "|---|---|"] + ["| [`%s`](engines/%s/) | %s |" % (k, k, desc.get(k, "Standalone engine")) for k in sorted(counts)]
    rc = HERE / "receipts.md"
    proof = rc.read_text(encoding="utf-8") if rc.exists() else "_Receipts are captured with capture_receipts.py._"
    (out / "README.md").write_text(README.format(n_eng=len(counts), eng_table="\n".join(rows), proof=proof), encoding="utf-8")
    (out / "ATTRIBUTION.md").write_text(ATTRIBUTION, encoding="utf-8")
    banner = HERE / "banner" / "nexxus_banner_1280x640.png"
    if banner.exists():
        (out / "assets").mkdir(exist_ok=True)
        (out / "assets" / "banner.png").write_bytes(banner.read_bytes())
    lic =HERE / "LICENSE_CC-BY-4.0.txt"
    if lic.exists():
        (out / "LICENSE").write_bytes(lic.read_bytes())
    (out / "docs").mkdir(exist_ok=True)
    (out / "docs" / "SPECIFICATION.md").write_text(SPEC.replace("@@N@@", str(len(counts))), encoding="utf-8")
    (out / "docs" / "ASSIGNMENT.md").write_text(ASSIGNMENT, encoding="utf-8")
    for area, text in AREA_READMES.items():
        if (out / area).is_dir():
            (out / area / "README.md").write_text(text, encoding="utf-8")
    lines = ["# Structure", "", "The complete public layout: **folder and file names only**. Every file is a one-line placeholder; the implementation is private.", "",
             "- `engines/<name>/` - one standalone, self-contained engine per folder", "- `core/` - the NEXXUS core", "- `bridge/` - the server, shared gateway and guardian",
             "- `dashboard/` - the user interface", "", "```"]
    dirs = {}
    for f in files:
        if f in ("README.md", "STRUCTURE.md"):
            continue
        dirs.setdefault(str(Path(f).parent).replace("\\", "/"), []).append(Path(f).name)
    for d in sorted(dirs):
        lines.append(d + "/")
        shown = dirs[d]
        lines += ["    " + n for n in shown[:60]] + (["    ... and %d more" % (len(shown) - 60)] if len(shown) > 60 else [])
    lines.append("```")
    (out / "STRUCTURE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"engines": counts, "files": len(files), "out": str(out)}


README = """![NEXXUS.ai](assets/banner.png)

# Autonomous Automation AI Infrastructure and Orchestrator

**NEXXUS: architecture playbook**

> **Coming soon: a free starter kit (about 2 to 3 weeks, maybe sooner).** A small, runnable core (the bridge port, its bridges, a local LLM and a search engine) for you to build on. Until then the **blueprint skeleton** in this repository is open to everyone: study it, copy it, build on it (see the Licence section).

> ### "My time is money. My product is free."
>
> *The core philosophy of this repository.*

> A modular, local-first AI ecosystem made of **{n_eng} standalone engines**, one **bridge**, and a private **core**.
> This repository is the *map*, not the territory: you can see exactly how the system is organised, and none of the implementation.

## What it is: in my words, and in formal terms

| In my words | The formal technical equivalent |
|---|---|
| **Autonomous Automation** | **Agentic workflow automation** with bounded autonomy and human-in-the-loop governance |
| **AI Infrastructure** | **Self-hosted, local-first AI infrastructure**: a local model-serving runtime plus a modular multi-engine service platform on a single node |
| **Orchestrator** | **Orchestration layer / control plane**: hub-and-spoke service orchestration through a single gateway, with a policy-enforcement (guardian) layer |
| **The whole system** | **A self-hosted, local-first, multi-engine AI orchestration platform** (SaaS-free, zero-cloud local orchestration) |

**In one sentence:** a **SaaS-free, local-first AI infrastructure**: a **modular multi-engine architecture** with **zero-cloud local orchestration**,
**hub-and-spoke integration through a single gateway**, and **human-in-the-loop governance**, running as a **single-node, vertically scaled** system.

## Distribution model: infrastructure, not handouts

**You are getting the sovereign orchestration framework and its empty utility skeletons. You are not getting proprietary, plug-and-play source code.**

| What you get | What you do not get |
|---|---|
| The **sovereign orchestration framework**: layout, boundaries, principles and the specification | Proprietary, plug-and-play engine source code |
| **Empty utility skeletons**: the folder and file structure of every engine, as placeholders | The internal wiring, configuration or data of the reference build |
| A **proven reference**: proof-of-life receipts from a real, local, cloud-free build | A hand-held tutorial, or a script that "just works" |

**The engineering standard.** The architecture is engineered to stand on its own and to run entirely on local hardware with no cloud: the reference build does exactly
that (see the proof-of-life receipts). But a skeleton is only a skeleton. **The implementation, and the execution of it, depend entirely on the builder's capability.**

**Reality check.** This is strictly local-first infrastructure with empty utilities. If you rely on cloud crutches, outsourced APIs, or a hand-held tutorial script,
**this build is not for you.** If you can build, it is the foundation to build on.
If you would rather pay the architect than do the work, see **Industrial Build & Enterprise Licensing** below.

## The assignment: command your own local AI

This repository is an **assignment, not a handout**. The framework is designed to stand up at its **bare minimum** (one gateway, one engine, one liveness check) and to grow from
there, and you do not need anyone's custom code to do it. You need the specification, a local AI and the willingness to put in the work: **wire up the utilities by working directly with your
own local AI**. By the end you will know how to command a local AI infrastructure, because you built it, and the architecture will have proved itself on your own machine.

Start here: [`docs/ASSIGNMENT.md`](docs/ASSIGNMENT.md), including a ready-to-adapt instruction template for your local AI.

## Original by design (a bespoke, from-scratch custom architecture)

**Built from the ground up. Not a fork, not a template, not a wrapper around someone else's agent framework** (no LangChain-style orchestration layer underneath).

Every engine and the core shown here was designed and written from scratch for this project, around one builder's needs, starting from a blank folder. It stands on
well-established architectural ideas (**modularity, a single API gateway, separation of concerns**) and the particular **composition** is its own:
{n_eng} isolated engines behind one bridge port, a private core, and a public facade that shows the structure while the implementation stays private.
You are looking at a **completely independent, sovereign framework**, not a configuration of a product you can buy.

## Free, local-first, and yours (SaaS-free local AI infrastructure)

**No subscriptions. No required cloud service. No vendor you cannot walk away from.**
Cutting the cloud cord means a **SaaS-free, zero-cloud, self-hosted** stack: **vendor-neutral, with no lock-in**.

This is infrastructure designed to give a developer **computational sovereignty** (**data and compute sovereignty, on-prem / edge by design**): it runs on your
own hardware, it is built from free and self-hosted parts, and nothing in it is load-bearing on a service that someone else can switch off or reprice. Any connection to
the outside world is optional and is always your decision. It is built in the spirit of open source: the architecture is published for anyone to study, copy and build on
(see the licence below).

## What is shared, and what is not

I am giving away the **sovereign, local-first infrastructure design**, completely free, to prove it can be done. To be absolutely clear about what that means:

| Provided here, free | Not provided |
|---|---|
| The infrastructure layout: engines, core, bridge, dashboard (the **reference architecture**) | The engine source code |
| The public facade: every folder and file name, as a map (an **interface-only publication**) | The proprietary internal bridge-wiring files: these stay **strictly private, personal IP** |
| The architecture, its boundaries and the reasoning behind them | Private configuration, data and secrets |

**You will structure and write your own underlying code.** This repository gives you the blueprint and the proof that the approach works; the
building is yours to do.

## Why this repository exists

Most architecture write-ups are either slide decks with no substance or source dumps with no map. This one publishes the **shape** of a real,
running system - its folders, its boundaries, its separation of concerns - and deliberately withholds the code behind it.

That is the **facade / core separation** (the **Facade pattern applied at repository level**: public interface, private implementation, **information hiding**):

| | Public (this repo) | Private (the real system) |
|---|---|---|
| What you see | Folder layout, names, boundaries, this overview | Implementation, configuration, data, secrets |
| Purpose | A reference for modular, decoupled design | The working system |
| Every source file here | A one-line placeholder | The real code |

## The idea in one picture (how the engines snap together)

```
   +--------+  +--------+  +--------+  +--------+           +--------+
   | engine |  | engine |  | engine |  | engine |   . . .   | engine |      {n_eng} standalone engines
   +---+----+  +---+----+  +---+----+  +---+----+           +---+----+      (each one is a self-contained folder)
       |           |           |           |                    |
       |    engines never talk to each other directly            |
       v           v           v           v                    v
   +-------------------------------------------------------------------+
   |                          B R I D G E   P O R T                    |   <- the one and only door
   +----------------------------------+--------------------------------+
                                      |
                +---------------------+---------------------+
                |                                           |
         +------+-------+                            +------+-------+
         | NEXXUS core  |                            |  dashboard   |
         +--------------+                            +--------------+
```

**How the engines snap together:** a **modular multi-engine architecture** with **zero-cloud local orchestration**. Every engine connects through one
**single gateway (the bridge port)** in a **hub-and-spoke topology**, so there is no engine-to-engine coupling.

## Proof of life: verified local multi-engine orchestration

No cluster. No cloud service required. One machine. These are not mock-ups: both receipts below were **generated from real runs** by a capture script that refuses to
write anything if a single check fails. Only results are shown, never code.

These receipts describe the **reference build**. They are evidence that this architecture runs locally, with no cloud; they are not a claim that this repository is runnable.

{proof}

## Principles

1. **Autonomous engines** (**loosely coupled, process-isolated service modules**). Every engine is a complete folder that stands on its own. Nothing outside it needs to know how it works inside.
2. **One door** (**a single point of ingress: the API-gateway / hub-and-spoke pattern**). Engines do not call each other. Everything that crosses a boundary crosses it at the bridge port, so the whole system has a single
   place to observe, guard and change.
3. **A sovereign core** (**orchestrator / control plane**). The core decides; engines advise and execute. The design goal is that taking one engine away does not stop the others.
4. **Local-first and subscription-free** (**local-first software, SaaS-free, zero-cloud orchestration**). Designed to run on your own hardware, with free, self-hosted components. No subscription and no cloud service is required.
5. **Humans approve growth** (**human-in-the-loop (HITL) governance, approval-gated capability onboarding**). New capabilities are proposed, explained in plain language, and only added after an explicit owner decision.
6. **Structure is public, implementation is private** (**the Facade pattern at repository level**). Boundaries are safe to show. Internals are not.

## Capacity and limits: the hardware envelope

This is a **local, sovereign, zero-subscription powerhouse**, and it runs on **single-machine physics**: the CPU, the RAM and, where you have one, the local GPU set the
ceiling. Think of an "unlimited" mobile plan. You get massive, high-performance capability, but push past a certain threshold of **heavy concurrent local generation** and you hit
the hardware wall.

In technical terms: **resource-bound, concurrency-limited local inference on a single node, scaled vertically** (better hardware, not more machines).

| It is built for | It is not built for |
|---|---|
| **Absolute personal sovereignty** and high-level **autonomous development** on one machine | **Infinite multi-node cloud scaling out of the box**: no horizontal scaling, no cluster scheduler, no cross-machine failover |
| Running with **no subscription or licence fee** | A promise of "zero cost": the hardware and the electricity are yours |

The reference system is a modest desktop: a dual-core CPU, about 8 GB of RAM, integrated graphics and no discrete GPU. It runs every engine and the local models.
That is the floor, not the ceiling. The full envelope is in [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md).

## Why I am sharing it: paying it forward

I am releasing this to pay it forward and to give everyone an opportunity to build. It proves that **independent, sovereign architecture can be done**:
by one builder, on ordinary hardware, without a subscription or a platform behind it.

**You are free to use this open infrastructure.** Take the folder structure, the boundaries and the "engines behind one bridge port" idea, write your
own engines and your own wiring, and make it yours.

**One personal request.** If it works for you, all I ask is that you make a short video acknowledging that the architecture worked and point people
back to this repository, so that everyone watching has the same opportunity to build for free. The video is a request; the **credit and link are a licence
condition** (see Licence, attribution and commercial use below).

## How to read this repository

| Folder | What it is |
|---|---|
| [`engines/`](engines/) | The {n_eng} standalone engines (self-contained **service modules**), one folder each |
| [`core/`](core/) | The NEXXUS core (the **orchestrator / control plane**) |
| [`bridge/`](bridge/) | The bridge side: the server, the shared gateway (**integration hub**) and the guardian |
| [`dashboard/`](dashboard/) | The user interface (**presentation layer**) |
| [`docs/ASSIGNMENT.md`](docs/ASSIGNMENT.md) | The assignment: how to command your own local AI to build and wire the utilities |
| [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md) | The architecture specification: integration path, capacity and limits, what is online and what is not |
| [`STRUCTURE.md`](STRUCTURE.md) | The complete folder and file layout |

Open any file and you will find a single line saying the implementation is withheld. That is expected: the **names and the layout** are the content.

## The engines

{eng_table}

## FAQ

**Can I run this?** Not from this repository: it contains the layout, not the code. You are free to use the layout to build your own.

**Why publish it at all?** To share a working example of how a large modular system can be organised (**modular, decoupled, local-first AI architecture**), and to invite discussion about the design.

**Is the real code open?** No. The implementation lives in private repositories and is available only under the Industrial Build agreement (see Industrial Build & Enterprise Licensing).

**Does it scale across many machines?** Not out of the box. It is a single-node, vertically scaled design: more capability means better hardware on the same machine. Scaling out
would be a different architecture that you would design and build yourself.

**Can I copy and build on the design?** Yes. That is the point. See the licence below.

**Why is the code private if the idea is free?** The design is the part that can be shared safely and usefully. The implementation contains private
configuration and wiring that is specific to one machine and one owner.

## Acknowledgments

**Google and Gemini: the core architectural partner.** A tribute to the free intelligence layer that helped collect the thoughts, structure the engine parameters and co-architect this
system from the ground up. Gemini was a **design-time partner**: nothing in the running system depends on it.

**Hugging Face**, the open hub that makes models, datasets and tooling accessible to everyone. **Llama**, the open-weight models from Meta that make serious local inference possible on ordinary hardware.

Together they are the trifecta of the **open and accessible stack** that made sovereign, local-first infrastructure possible.
Product names and marks belong to their owners; their mention here is gratitude, not endorsement by them.

## Licence, attribution and commercial use

**Open for study and integration. Attribution is mandatory.**

This skeletal framework and blueprint (the layout, names and documentation in this repository) are licensed under
[**Creative Commons Attribution 4.0 (CC BY 4.0)**](https://creativecommons.org/licenses/by/4.0/). You may study them, copy them, integrate them and build on
them, **including commercially, with no fee and no royalty**. There is one condition, and it is not negotiable:

> **Any commercial, monetized or profit-driven deployment built on this architecture must credit the original author and name this repository as the
> source of the architecture.**

If you commercialize it, you do so *without reimbursing the author*, and that is precisely why the credit is **strictly required**. In practice:

1. **Credit the original author** (the owner of this repository).
2. **Link to this repository** as the source of the architecture, wherever you present the product or its documentation (site, docs, README, launch material).
3. **Indicate what you changed.**

A suitable credit line:

> *Architecture based on "NEXXUS: Autonomous Automation AI Infrastructure and Orchestrator" by the original author (link to this repository), licensed under CC BY 4.0.*

Failure to give credit ends your right to use the material under the licence (CC BY 4.0, section 6). Using it without credit is not "borrowing the idea": it is use
without permission.

**Authorship record.** The dated, public commit history of this repository is a timestamped record of the authorship and first publication of this architecture.
It stands as public evidence of who published this design, and when.

**What the licence does not cover.** The private implementation, including the internal bridge-wiring files, is not covered by this licence, is not published,
and remains private personal IP; it is available only under the Industrial Build agreement below. Publishing this repository does not transfer ownership of anything: the author keeps the copyright.

## Industrial Build & Enterprise Licensing

**Build it yourself, free. Skip the work, pay the architect.**

> ### "My time is money. My product is free."
>
> *The core philosophy of this repository.*

The purpose of this repository is that **you build it yourself**. The blueprint is free so that you can learn, put in the reps and produce the product on your own. That is the goal, and nothing
here is withheld to force a sale.

The **Industrial Build** exists for those who choose not to do that work. It is a **service**, and its price is **the master architect's fee**.

### What the $10,000 is, and what it is not

It pays for **my time, my engineering services and my custom architecture, packaged as a turnkey setup**: designed, wired, verified and installed on hardware you control.
It is **not** a charge for raw files, and it is **not** a charge for third-party models or libraries. Those stay under their own licences and are never resold; the build is configured
for components you are licensed to use for your purpose.

| | **DIY: this repository** | **Industrial Build** |
|---|---|---|
| Price | Free (CC BY 4.0) | **$10,000, one time, per licence**: an engineering-services fee |
| You receive | The framework, the empty skeletons, the specification, the assignment | The reference implementation, delivered turnkey: engines, bridge wiring, guardian, dashboard |
| Who builds it | **You**, with your own local AI | **Delivered built** and installed on hardware you control |
| Contract | None | **Mandatory digital licence and confidentiality agreement** |
| Support | None | Optional **$1,000 per month** retainer |
| Built for | Builders who want the skill and the product | Businesses that want the result without the build |

### Who it is for

Businesses and serious operators who would rather pay for the architect than spend the time to build, and who can sign a business agreement. **If you want to learn it, build it: the free path is
the real thing.** The Industrial Build is sold to **businesses only**.

### Mandatory digital contract

**Nothing is delivered before the agreement is signed.** One document carries both the software licence and the confidentiality terms, executed digitally by an **authorised signatory** of the
purchasing business, with the signatory's name, title and legal entity recorded. The signed agreement is the only source of binding terms; this page is a summary of it, not a substitute for it.
Terms change only by written addendum.

### Single-user licence

One licence covers **one named user** operating **one installation** on hardware the licensee controls. It is **non-transferable and non-sublicensable**. Additional users, installations or
sites each require a further licence, by addendum. The licence is **perpetual for the delivered version**: it keeps working if you never buy support.

### Anti-redistribution and confidentiality

No copying beyond internal backups, no resale, no sublicensing, no sharing with third parties, no hosting it as a service for others, no publishing or disclosing it or its materials, no
removing notices, and no using it to build a competing product for distribution. **Every delivery is individually identified**, and the agreement grants **audit rights**: a leak is traceable
to its source. Confidentiality obligations survive termination.

### Tiered consequences

| Tier | Breach | Consequence |
|---|---|---|
| 1 | Use beyond the licensed scope (more users, installations or sites) | Billed at the then-current licence price for the excess, from the date it began, and brought into compliance |
| 2 | Disclosure of confidential material, or breach of the confidentiality terms | Licence termination, return and destruction of all copies, injunctive relief, and damages including enforcement costs |
| 3 | Redistribution, resale, sublicensing or publication of the build | Everything in tier 2, plus liquidated damages as defined in the agreement |

Amounts and mechanics are set out in the agreement alone. They are designed to be proportionate and enforceable, not decorative.

### Support retainer

**$1,000 per month, optional.** It buys updates and security fixes for the delivered build, direct engineering help within a defined scope, and response targets that are written into the
agreement. Remote sessions happen only when you start them and only as long as you allow. **The retainer is never a runtime dependency**: if it stops, the system keeps running; you lose
updates and support, not the build.

### Third-party components

Open and third-party components keep their own licences and are delivered with their notices. They are not sold, not relicensed and not covered by the Industrial Build agreement.

### Inquiries

Contact the repository owner through their GitHub profile. State your business, your intended use and the number of users. This section is a summary of an offering, not an offer capable of
acceptance, and not legal advice.
"""

SPEC = """# Autonomous Automation AI Infrastructure and Orchestrator: architecture specification

**NEXXUS**, specified.

This is the public specification of the **layout and the limits** of a local-first, SaaS-free multi-engine system. It describes the design. It contains no implementation.

## Distribution model: infrastructure, not handouts

**This specification describes the sovereign orchestration framework and its empty utility skeletons. It does not include proprietary, plug-and-play source code.**

| What you get | What you do not get |
|---|---|
| The **sovereign orchestration framework**: layout, boundaries, principles and the specification | Proprietary, plug-and-play engine source code |
| **Empty utility skeletons**: the folder and file structure of every engine, as placeholders | The internal wiring, configuration or data of the reference build |
| A **proven reference**: proof-of-life receipts from a real, local, cloud-free build | A hand-held tutorial, or a script that "just works" |

**The engineering standard.** The architecture is engineered to stand on its own and to run entirely on local hardware with no cloud: the reference build does exactly
that (see the proof-of-life receipts). But a skeleton is only a skeleton. **The implementation, and the execution of it, depend entirely on the builder's capability.**

**Reality check.** This is strictly local-first infrastructure with empty utilities. If you rely on cloud crutches, outsourced APIs, or a hand-held tutorial script,
**this build is not for you.** If you can build, it is the foundation to build on.
If you would rather pay the architect than do the work, see **Industrial Build & Enterprise Licensing** below.

## 1. Overview

| In my words | The formal technical equivalent |
|---|---|
| **Autonomous Automation** | **Agentic workflow automation** with bounded autonomy and human-in-the-loop governance |
| **AI Infrastructure** | **Self-hosted, local-first AI infrastructure**: a local model-serving runtime plus a modular multi-engine service platform on a single node |
| **Orchestrator** | **Orchestration layer / control plane**: hub-and-spoke service orchestration through a single gateway, with a policy-enforcement (guardian) layer |
| **The whole system** | **A self-hosted, local-first, multi-engine AI orchestration platform** (SaaS-free, zero-cloud local orchestration) |

In detail: a **modular multi-engine architecture** with **zero-cloud local orchestration**, designed for **personal sovereignty** (**data and compute sovereignty, on-prem / edge**) and
**high-level autonomous development** on **one machine**. @@N@@ standalone engines connect through a single gateway (**hub-and-spoke**); a private core orchestrates;
a guardian verifies what may pass or run; a dashboard presents it all.

## 2. Components

| Component | Role | Technical term |
|---|---|---|
| Engines | Self-contained units of capability, one folder each | Loosely coupled, process-isolated service modules |
| Bridge | The one door every cross-boundary message uses | Gateway / integration hub (hub-and-spoke) |
| Core | Decides, plans and delegates | Orchestrator / control plane |
| Guardian | Verifies messages, tracks drift, decides what may run | Message-integrity and policy enforcement layer |
| Dashboard | The user interface | Presentation layer |

## 3. Integration path (for anyone building their own)

1. **Size the machine.** Decide your hardware envelope first (section 4). Everything else follows from it.
2. **Run a local model runtime.** Any self-hosted runtime works. Choose models your RAM can hold.
3. **Make each engine an autonomous folder** with its own entry point. Nothing outside an engine should need to know how it works inside.
4. **Put one gateway in front.** All cross-boundary traffic goes through it; engines never call each other. You gain a single place to observe, guard and change the system.
5. **Verify before you trust.** Treat every message and every new capability as untrusted until it has been verified or explicitly approved by a human (**human-in-the-loop governance**).
6. **Keep the interface self-contained.** Bundle its assets so that it loads nothing from the internet at startup.
7. **Prove it.** Write automated checks for liveness *and* behaviour. A component that is "up" has proved only that it is up.

You write your own engines and your own wiring, by working with your own local AI. The proprietary wiring of this system is private and is not part of this specification.
The guide for doing that is [`ASSIGNMENT.md`](ASSIGNMENT.md).

## 4. Capacity and limits: the hardware envelope

**Contract.** This design is a **local, sovereign, zero-subscription powerhouse** that runs on **single-machine physics**. The CPU, the RAM and, where present, the GPU and its memory set
the ceiling. It behaves like an "unlimited" plan: very high capability, but past a threshold of **heavy concurrent local generation** you hit the hardware wall.
It is built for **absolute personal sovereignty and high-level autonomous development**, not for **infinite multi-node cloud scaling out of the box**.

**Reference system.** A dual-core desktop CPU in the 3 GHz class, about 8 GB of RAM, integrated graphics, no discrete GPU, a mainstream desktop operating system, models running on the CPU.
The complete system, with all engines live, runs on it. Treat that as the floor.

**Concurrency is bounded by design**, so that the machine degrades by queuing instead of failing:

| Resource | Behaviour |
|---|---|
| Model generation while building | One call at a time; others wait their turn |
| Background jobs | A small worker pool; the rest queue |
| Sandboxed capability runs | Two at a time, with per-call time, memory and output limits, and a per-minute rate limit |
| Model memory | Models stay loaded for a while after use; switching modes swaps models, which costs time on a CPU |

**What the wall looks like.** Chat alongside one build works. Many builds, a large model and many busy engines at once will queue, slow down, or exhaust RAM and start swapping to disk.
Latency grows long before anything fails outright.

**Raising the ceiling (vertical scaling).** More RAM, a fast SSD, a discrete GPU with enough video memory, a larger model, larger worker pools. Each is a change on the same machine.

**Not provided (horizontal scaling).** No cluster scheduler, no shared state across machines, no cross-machine authentication, no failover. Running across several machines is a
different architecture that you would design and build. A single machine is also a **single point of failure**: back it up.

"Zero cost" means no subscription or licence fee. The hardware and the electricity are yours.

## 5. Zero-cloud, and its exact boundary

Nothing in the system requires a cloud service to run, and the dashboard **loads nothing from the internet**: its 3D library and visuals are bundled with it.
A small number of features reach the internet **only when you start them**, and every one of them can be left off:

1. Fetching an open-source capability from a public code host, after which a human approves it.
2. Web search and recon: the dashboard search box, the chat search command, and a scrape pipeline against a target you name.
3. Remote access through a private network tunnel, if you set one up.
4. Installing the packages a capability needs: you run the command yourself.

## 6. What is and is not provided

| Provided, under CC BY 4.0 | Not provided |
|---|---|
| This specification, the layout, the boundaries and the reasoning | Engine source code, except under the separate Industrial Build agreement |
| The public facade: every folder and file name as a map | The proprietary internal wiring |
| | Configuration, data and anything private |

## 7. Telemetry and proof

The reference build publishes proof-of-life receipts (see the README): live component counts, verified-message counts and master-suite results, generated from real runs, results only.
They describe the **reference build** and are evidence that the architecture runs locally with no cloud. They are not a claim that this repository, which holds only skeletons, can be run as is.

## 8. Acknowledgments and third-party credit

**Google and Gemini: the core architectural partner.** A tribute to the free intelligence layer that helped collect the thoughts, structure the engine parameters and co-architect this
system from the ground up. Gemini was a **design-time partner**: nothing in the running system depends on it.

**Hugging Face**, the open hub that makes models, datasets and tooling accessible to everyone. **Llama**, the open-weight models from Meta that make serious local inference possible on ordinary hardware.

Together they are the trifecta of the **open and accessible stack** that made sovereign, local-first infrastructure possible.
Product names and marks belong to their owners; their mention here is gratitude, not endorsement by them.

The dashboard's 3D view uses **Babylon.js**, licensed under the Apache License 2.0, bundled with the private dashboard.
"""

ASSIGNMENT = """# The assignment: command your own local AI infrastructure

This is an **assignment, not a handout and not a tutorial script**. It tells you what to build and how to command your own local AI to build it. It does not build it for you.
Doing the work is the point: by the end you will know how to run a local AI infrastructure because you made one, and your own checks will show that the architecture works.

## The bare minimum (a design principle)

The framework is designed to stand up at its **bare minimum** and grow from there:

1. **One gateway** that accepts a message, verifies it and routes it.
2. **One engine**, an autonomous folder with its own entry point.
3. **One liveness check**: the engine reports in, and the gateway can tell it is alive.

That is a working system. Everything else (more engines, a guardian, a dashboard, human approval for new capabilities) is additive. You do not need anyone's proprietary code for any of it.
This public repository holds the skeleton and the specification, not runnable code: **the reference build proves the approach, and the work of building yours is yours.**

## Step by step

0. **Read the hardware envelope** in the specification, and size your machine and your model to it before anything else.
1. **Run a local model runtime** (any self-hosted runtime) and choose a model your RAM can hold. Start small. A small model that fits beats a large one that swaps to disk.
2. **Create the skeleton**: copy the folder layout from `STRUCTURE.md` as empty files. The structure is the plan.
3. **Give your AI the specification** and one folder at a time. Keep the context small: small models lose the thread in long conversations.
4. **Build the gateway first.** It is the smallest piece and everything depends on it.
5. **Build one engine**: an entry point and a heartbeat.
6. **Write the check before the feature.** For every utility, write a check that proves it works, and a check that proves a bad input is refused.
7. **Wire utilities one at a time.** Review every change yourself, run the checks, and commit when green.
8. **Add the guardian and human approval** once the basics are green: verify before you trust, and let a human approve new capabilities.

## How to command a small local AI (what actually works)

- **One task per request.** Describe the interface first (inputs, outputs, what must be refused), then ask for the code.
- **Ask for the check with the code**, and ask how to run it. Paste real error output back, not a description of it.
- **Ask for complete files**, not fragments, so nothing is silently dropped.
- **Distrust confident answers.** Local models make confident mistakes. Read the code before you run it. Never run generated code you do not understand.
- **Keep everything under version control**, so any bad suggestion can be undone.
- **Stay offline.** The point of the infrastructure is that it does not need a cloud; do not hand your build to one.

## Instruction template for your local AI (copy and adapt)

```
You are my local engineering assistant. Work only inside the folder I name in each task.

Rules:
1. Make one small change at a time.
2. Show the complete file, never fragments.
3. Write a check that proves the change works, and tell me exactly how to run it.
4. Never touch anything outside the folder named in the task.
5. Never add a dependency without telling me its name and why.
6. Never contact the internet or any cloud service.
7. If a request is unclear, ask me one question before writing code.
8. After each change, list what could break.

Context: I am building a local-first system with a single gateway and autonomous engines.
The specification is below. Task: <describe one small task here>
```

## Definition of done

- [ ] The gateway is running and refuses a message it cannot verify.
- [ ] One engine reports alive, and the gateway can see it.
- [ ] One message travels end to end through the gateway.
- [ ] A deliberately bad message is refused, and a check proves it.
- [ ] You can stop and restart everything and it comes back.
- [ ] You wrote your own results readout, and it is honest: it only reports what it measured.

## Honest expectations

Building this takes real engineering time, and local AI on modest hardware is slow and fallible. If your plan depends on cloud services, outsourced APIs, or a script that does the work for
you, this is not the right foundation. If you can build, it is.
"""

ATTRIBUTION = """# Attribution

If you build on this architecture, credit it. Copy and adapt this line:

> Architecture based on "NEXXUS: Autonomous Automation AI Infrastructure and Orchestrator" by the original author (link to this repository), licensed under CC BY 4.0.

Commercial and profit-driven use is welcome and free of charge. Attribution is mandatory: credit the original author, link this repository as the
source of the architecture, and indicate your changes. The full terms are in the Licence section of the README.
"""

AREA_READMES = {
    "engines": "# Engines\n\nStandalone engines. Each folder is a complete, self-contained unit. The implementation is private.\n",
    "core": "# Core\n\nThe NEXXUS core. The implementation is private.\n",
    "bridge": "# Bridge\n\nThe bridge side of the system: the server, the shared gateway and the guardian. The implementation is private.\n",
    "dashboard": "# Dashboard\n\nThe user interface. The implementation is private.\n",
}


# ------------------------------------------------------------------------------------------------------------- the leak guard
def verify(out=OUT):
    out = Path(out)
    problems = []
    if not out.is_dir():
        return ["output folder does not exist"]
    src_hashes = set()
    for root in (WORK / "axis-ui-interface", WORK):
        for p in list(root.glob("*.py"))[:400]:
            try:
                src_hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
            except OSError:
                pass
    generated = {"README.md", "STRUCTURE.md", "ATTRIBUTION.md", "docs/SPECIFICATION.md", "docs/ASSIGNMENT.md", "LICENSE"}
    for p in out.rglob("*"):
        if not p.is_file() or ".git" in p.parts:
            continue
        rel = p.relative_to(out).as_posix()
        if rel == "assets/banner.png":                               # the one allowed binary: the generated banner
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        if HIDE_NAME.search(rel):
            problems.append("hidden name present: " + rel)
        if SECRET_CONTENT.search(txt.replace("-", "") if rel == "STRUCTURE.md" else txt) and rel not in generated:
            problems.append("secret-shaped content: " + rel)
        if hashlib.sha256(p.read_bytes()).hexdigest() in src_hashes:
            problems.append("byte-identical to a source file: " + rel)
        is_doc = rel in generated or rel.endswith("/README.md")
        if not is_doc and txt not in PLACEHOLDERS and txt not in _known_placeholders():
            problems.append("not a placeholder (could be implementation): " + rel)
        if p.stat().st_size > 60_000 and rel != "LICENSE":
            problems.append("unexpectedly large: " + rel)
        parts = Path(rel).parts
        if parts[0] in ("bridge", "core") and len(parts) > 1 and any(BRIDGE_HIDE.search(x) for x in parts[1:]) and rel != "bridge/README.md":
            problems.append("bridge side contains a wiring-style name: " + rel)
        if parts[0] == "engines" and len(parts) > 1:                 # ISOLATION: nothing inside an engine may hint at the bridge
            if any(WIRING_NAME.search(x) for x in parts[2:]):
                problems.append("engine contains a wiring-style name: " + rel)
            if WIRING_CONTENT.search(txt):
                problems.append("engine file mentions the bridge or its wiring: " + rel)
    for rd in [out / "README.md"] + sorted((out / "docs").glob("*.md")):
      if rd.exists():
        t = rd.read_text(encoding="utf-8")
        name = "README" if rd.name == "README.md" else rd.relative_to(out).as_posix()
        for rx, why in ((r"(?i)localhost|127\.0\.0\.1|\b\d{1,3}(\.\d{1,3}){3}\b", "a host or address"), (r"\bport\s*:?\s*\d{2,5}\b|:\d{4,5}\b", "a port number"),
                        (r"[A-Za-z]:\\|/Users/|\\Users\\", "a local path"), (r"\b[\w-]+\.(py|bat|ps1|sh|json|secret|env)\b", "a file name"),
                        (r"(?i)consult|keybox|\.env|secret\b|token", "a private subsystem or secret term"), (r"(?i)\bjamal\b|mccarthy", "a personal name")):
            m = re.search(rx, t)
            if m:
                problems.append("%s leaks %s: %r" % (name, why, m.group(0)[:40]))
    for e in (out / "engines").iterdir() if (out / "engines").is_dir() else []:
        if e.is_dir() and not (e / "README.md").exists():
            problems.append("engine without its README: " + e.name)
    return problems


def _known_placeholders():
    return {placeholder(e) for e in list(COMMENT) + [".json", ".md", ".txt"]}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"
    if cmd == "audit":
        r = audit()
        print("%-24s %6s %9s %14s %8s" % ("engine", "files", "own+clean", "own-but-wired", "wiring"))
        for k, v in r.items():
            print("%-24s %6d %9d %14d %8d" % (k, v["files"], v["own_clean"], v["own_but_mentions_bridge"], v["wiring_files"]))
        print("\ntotals: files=%d clean=%d mention-bridge=%d wiring-files=%d" % tuple(sum(v[k] for v in r.values()) for k in ("files", "own_clean", "own_but_mentions_bridge", "wiring_files")))
    elif cmd == "build":
        info = build()
        print("built %d placeholder files for %d engines into %s" % (info["files"], len(info["engines"]), info["out"]))
        bad = verify()
        print("LEAK GUARD: %s" % ("CLEAN" if not bad else "%d problem(s)" % len(bad)))
        for b in bad[:40]:
            print("  -", b)
        sys.exit(1 if bad else 0)
    elif cmd == "verify":
        bad = verify()
        print("LEAK GUARD: %s" % ("CLEAN" if not bad else "%d problem(s)" % len(bad)))
        for b in bad[:40]:
            print("  -", b)
        sys.exit(1 if bad else 0)
