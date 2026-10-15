# Engine Build Mode, engine telemetry and the Prompt Recipe Vault

Three additions to the NEXXUS dashboard. All of it is local, standard library only, and covered by tests (`python verify_all.py`).

## Engine Build Mode (bottom-left mode selector)
Pick **Mode: Engine Build**. Two controls appear beside the selector: the **Standalone / Linked** switch and the **Engine tracker** button.
Then order an engine in the command box: *"build an engine that ..."*.

1. **Mapping.** NEXXUS reads its own local file structure first (`workspace_map.py`): every core `.py` file by name, docstring line, classes, functions and imports (read with
   `ast`, never imported or run), plus the modules that already exist (name, port, host, linked or not). It never reads secrets, vaults, logs, environments, or file bodies.
2. **Scaffold.** A fixed, reviewed template writes the module: `module.json`, `server.py`, `engine/`, `index.html`, tests, README (`engine_templates.py`). Nothing here is model-written.
3. **The model writes the logic.** Only `engine/*.py` and `test_core*.py`. It cannot touch the server, the link, `module.json` or the secret.
4. **Tests run** (compile + every `test_*.py` in a child process, secrets stripped), with up to three fix rounds. **Audit** (AST, not regex): blocks `eval/exec/os.system/subprocess`,
   imports of NEXXUS kernel modules, NEXXUS secrets, and paths outside the folder; network use is a warning.
5. **Staged.** The finished build waits in `staging_vault/engines/<id>/`. Nothing is deployed. A build with no model, failing tests or a blocked audit can never be approved.
6. **You approve.** In the tracker, *Approve & deploy* sends the admin token and the briefing hash you were shown. The files are re-hashed; if anything changed, it is refused.
   Deployment copies the engine to `axis-ui-interface/<name>/` (never overwriting), re-runs its own tests in place (and removes everything if they fail), and the gateway starts it
   within about 10 seconds. The decision is written to a hash-chained ledger (`logs/engine_builds.jsonl`).

**Standalone vs linked.** Every engine is a module that runs on its own (like PICTHIS or the blog portal). *Standalone* means no NEXXUS link at all: no `nexxus_link.py`, no secret, no
`nexxus` block. *Linked* adds the gateway's external bridge: a signed, read-only door (`status`, `health`) with a secret kept only in the engine's folder. Either way the engine never
imports NEXXUS code and NEXXUS never imports the engine's, so the core kernel is not touched.

**The live tracker** (side drawer): the file tree appears as files are written (planned, writing, written, tested, deployed), click any file to read it, the log shows what is happening,
and the review panel holds the approve/reject buttons.

## Engine telemetry (Settings, and the lights in the header)
`engine_telemetry.py` registers every module in the UI directory (and the external roster), plus engine builds in progress. A light background loop (every 10 s) pings each one: a *linked*
module is asked "health" with the same signed request NEXXUS uses, so online really means answering across the bridge; a *standalone* module's plain health page is asked through the gateway.
The header shows one light per engine (green answering, red offline, amber building). When an engine sends a message, is called, comes online or goes offline, **its light flashes and a soft
tone plays** (each engine has its own pitch; routine heartbeats flash without sound). Settings has the full table, a mute, a volume slider and a test button.
Honest limit: browsers allow sound only after you have clicked or pressed a key on the page once.

## Prompt Recipe Vault (the [P] button beside the (i) button)
Ten built-in architectural recipes (the module contract, a linked engine, a SQLite data engine, a parser, a scheduler, an API client, a dashboard panel, map-first planning, tests-first
hardening, a review checklist) plus your own. *Insert* puts the text in the command box (nothing is sent); *Insert + switch* also changes to the mode it was written for. Saving or deleting
your own recipes needs the admin token; they live in `prompt_recipes.json` (git-ignored). The built-in ones cannot be deleted.

## Honest limits
* The quality of an engine's logic depends on the local code model (default `qwen2.5-coder:3b`); small models write small engines. With no model running the build stops at `needs_model`.
* The audit is a safety net, not a proof. That is why a human approves, and why the staged files are readable in the tracker before anything is deployed.
* A deployed engine runs with your user's permissions, like every module in `axis-ui-interface/`. Only approve what you have read.
