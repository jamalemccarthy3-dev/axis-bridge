# Push plan (next week)

State when this was written (2026-10-10): the repo on GitHub is **Private**. Everything since 2026-10-09 is committed locally and **not pushed**.
Bridge and utility code is untracked and git-ignored (names only in `PRIVATE_MODULES.md`). Old copies of that code are still in GitHub's history; that is fine
while the repo stays Private.

## Before you push
1. `python verify_all.py` should end with `ALL GREEN`.
2. `cd axis-ui-interface/project-X && python -m axis_gate verify` should say `nothing drifted`.
3. `git status` should show a clean tree; `git log origin/main..HEAD --oneline` lists what will go up (62 commits when checked on 2026-10-12; the plan used to say about 35).
   The two files git shows as changed or untracked (`Nexxus/state_logs/flow_state_manifest.json`, which the system rewrites, and `axis-ui-interface/counts_words/`, a real engine build
   from earlier) are not part of any commit; leave them out or decide about them separately.
4. Check GitHub still says Private: `gh repo view jamalemccarthy3-dev/axis-bridge --json visibility -q .visibility`
5. Scan history for keys: install gitleaks and run `gitleaks detect` in the repo (or ask Claude to run a pattern scan). Fix anything it finds BEFORE pushing.
6. The nested repos (`nexxus`, `axis-core`, `axis-vantage_point`, `triad-protocol-module-`) have their own history and are pushed separately, if at all.
   Check each one's remote with `git remote -v` first.

## The push
```
git push origin main
```
A normal push only adds commits; it does not delete anything on GitHub. Do not use `--force`.

## After you push
- Open the repo on GitHub and confirm it is still Private and that `PRIVATE_MODULES.md` is there but the `lib/` folders are not.
- Pushing makes the latest version drop the bridge and utility code. Older commits still contain it (Private, so only you can see it).

## picthis (its own repo: `C:\Users\Jamal\Desktop\picthis`)
picthis is a separate repo (`github.com/jamalemccarthy3-dev/picthis`). The push plan above does not push it; it needs its own push.

State when added (2026-10-10): the GitHub repo is **Private** (last push 2026-10-08). **4 commits are local and not pushed**: real 3D / animation / sound,
photo-to-3D framing, "use last converted model", and the music-mood and voice-style dropdowns. A pattern scan of its whole history found no keys, and no
user assets (`asset_vault`, `render_staging`, `staging_photos`) are tracked.

Before pushing picthis:
1. `cd C:\Users\Jamal\Desktop\picthis`, then `python test_picthis_3d.py` (about a minute) should end with `OK`, and `cd backend` then `python -m pytest -q test_backend.py` should pass.
2. `git status` is clean, and `git log origin/main..HEAD --oneline` shows the 4 commits.
3. Private check: `gh repo view jamalemccarthy3-dev/picthis --json visibility -q .visibility` must say `PRIVATE`.
4. Secrets: `.env`, `nexxus.secret`, `*.key`, `*.secret` and the generated folders are git-ignored. Confirm `git ls-files | findstr /i "secret .env"` shows nothing.
5. **Utility files are hidden (done).** picthis's `src/lib/*_tool.py`, `ui_bridge.py` and `ui_bridge_config.py` (12 files) are untracked and git-ignored like axis-bridge's;
   `PRIVATE_MODULES.md` lists their names only (`python private_manifest.py` regenerates it). They are still in the 2026-10-08 commit already on GitHub (Private, so only you
   can see them). A clone of the public side will not run without them; add the ones a starter pack needs with a `!path` line in `.gitignore`.
6. `git push origin main` (never `--force`).

After pushing: confirm on GitHub that it is still Private. Nothing generated (videos, meshes, the HuggingFace token in `.env`) is in the repo.
Going public later: same rule as above, make a clean starter-pack copy instead of flipping this repo.

## TheBlogGuyEngine and TheBlogGuy (two more separate repos on the Desktop)
Both are **Private** on GitHub (last push 2026-10-08), each with its own push.

* **TheBlogGuyEngine** (`github.com/jamalemccarthy3-dev/theblogguyengine`): its utility files are now hidden the same way (38 files untracked and git-ignored:
  all `*_utility*.py`, their configs, and `lib/`); `PRIVATE_MODULES.md` lists 37 names only. **1 local commit is not pushed.** Before pushing: `git status` clean,
  repo still Private, `git ls-files | findstr /i "secret .env"` shows nothing, then `git push origin main` (never `--force`). Old copies of those files are still in
  the commits already on GitHub (Private, so only you can see them).
* **TheBlogGuy** (`github.com/jamalemccarthy3-dev/theblogguy`): 8 small files, no utility files to hide, nothing local to push.

## Added 2026-10-10: Engine Build Mode, engine telemetry, Prompt Recipe Vault
* **Re-seal the axis gate first.** Three sealed core files changed on purpose (`python_server.py`, `nexxus_external.py`, `nexxus/mode_policy.py`), so `python -m axis_gate verify`
  reports DRIFT until you review and re-seal them (dashboard: Settings > axis gate > Re-seal, or `python -m axis_gate seal core` from `axis-ui-interface/project-X`, admin token).
  I did not re-seal them: that decision is yours.
* **The `nexxus/` repo has new local commits** (engine_build.py, engine_telemetry.py, engine_templates.py, prompt_vault.py, workspace_map.py, their tests). It pushes separately.
* `prompt_recipes.json` (your saved recipes) is git-ignored. `staging_vault/engines/` (staged engine builds) is already under the ignored `staging_vault/`.
* Restart the server (`restart_nexxus.bat`) so the running NEXXUS loads the new routes.

## Added 2026-10-10: Link mode (AXIS LINK)
* New `nexxus/` files (link_hub.py, link_translate.py, link_analyst.py, input_queue.py, test_link_hub.py) and a `link` entry in `mode_policy.py`: they push with the `nexxus/` repo.
* The sealed core files `python_server.py` and `nexxus_external.py` changed again, so the same re-seal applies (see above). Not re-sealed: your call.
* The two-slot input queue now sits in front of `/bridge` and `/command-dispatch` in every mode (a third message gets HTTP 429). Restart the server to load it.
* Details: `AXIS_LINK.md`.

## Added 2026-10-11: control dock, Perimeter overrides, admin-token dialog
* New root files `perimeter.py`, `test_perimeter.py`, `PERIMETER.md`; `python_server.py` and `nexxus_external.py` (sealed core files) changed again, so the same re-seal applies. Not re-sealed: your call.
* `perimeter_state/` (locks, breach log, quarantined packet copies) is git-ignored. Hard Lock refuses a node in NEXXUS's own server and bridge only; it never touches an engine.
* The admin token is now entered in an in-page dialog (`window.prompt` is not supported in the Claude app's browser pane, which is what left the key sequence stuck).

## Added 2026-10-11 (later): Flight Records and the strict-JSON fix
* Flight Records are the AXIS LINK ledger with Flight IDs and a per-flight diagnosis (`nexxus/link_hub.py`, `link_translate.py`, `python_server.py`, the Settings card): same sealed-file drift note as above.
* The `picthis` repo has new local commits: `backend/safe_json.py`, changes to `backend/server.py`, `backend/pipeline_worker.py`, `picthis.html` and `backend/test_json_payload.py`. It pushes separately.

## Added 2026-10-11 (naming + watch)
* New `nexxus/` files `naming.py`, `vital_watch.py`; edits in `creations_vault.py`, `creation_mode.py`, `engine_build.py`, `nexxus_talks.py`, `tool_vault.py` push with the `nexxus/` repo. Root: `NAMING_AND_WATCH.md`, `test_naming_watch.py`, `python_server.py`, `nexxus_external.py` (sealed-file drift note applies).
* `commercial_watch.json` (the list of files you want watched) is git-ignored: it names your sellable paths and must not be published. The `picthis` repo gets `backend/explicit_name.py` and tests.

## Added 2026-10-11 (intake pipeline)
* New `nexxus/intake_pipeline.py` and its tests; changes in `tool_vault.py` and `engine_build.py` push with the `nexxus/` repo. Root: `INTAKE_PIPELINE.md`, `test_intake_routes.py`, `python_server.py`, `link_translate.py` (in `nexxus/`).
* Staged tools now carry `upstream/` (as published), `pipeline.json` and `contribution_note.md`; `staging_vault/` is already git-ignored, so none of it is published.

## Added 2026-10-11 (portals, hub windows, hub chats, courier, axis-core learning)
* **Main repo:** new `portals.py`, `portal_chat.py`, `domain_dispatch.py`, `domain_hub_server.py`, `start_domain_hubs.bat`, `PORTALS.md`, `portal_data/` (the **SAMPLE** data and the editorial
  `hub_catalog.json` are tracked; each hub's `hub_<portal>.json` of what you added is git-ignored), three test files (registered in `verify_all.py`), plus edits to `python_server.py` and the
  dashboard page. Details and limits: `PORTALS.md`.
* **axis-core repo (pushes separately, 7 local commits):** `hub_search.py`, `knowledge.py`, `fuse.py`, their tests and `KNOWLEDGE.md`.
* **Private by your own rule:** `axis-logic/lib/economics.py` and `lib/logistics.py` live under the git-ignored `lib/` (like `markets.py`), so a clone of the public side cannot run
  `portal_worker.py` without them. Add them with a `!path` line if a starter pack needs the portals.
* **The home screen courier is ON by default.** In Conversation mode a prompt that clearly belongs to one hub is sent to that hub's port (8721 sports, 8722 markets, 8723 logistics,
  8724 economics, all on 127.0.0.1) and NEXXUS does not answer it itself. **Those four hub processes must be running** (`start_domain_hubs.bat`; they do not survive a reboot or a
  `restart_nexxus.bat`). With them down, a domain question on the home screen gets a plain "the X hub is not answering" message. Switch the courier off with `NEXXUS_DOMAIN_DISPATCH=0`.
  Adding the hub start to `restart_nexxus.bat` is a small change I have **not** made: it is your startup file.
* **Web search leaves the machine:** a hub chat's `search:` sends only the query text to DuckDuckGo (through the axis search engine). `NEXXUS_PORTAL_WEB_SEARCH=0` switches it off.
* **Not wired yet:** `knowledge.py` and `fuse.py` are tested libraries; nothing in the running server calls them.
* The sealed-file drift note above still applies (`mode_policy.py`, `tool_vault.py`, `nexxus_external.py` drift when checked 2026-10-11). Not re-sealed: your call.
* Restart the server (`restart_nexxus.bat`) to load the new routes; the hub processes only need restarting after a change to `portal_chat.py`.

## Checked 2026-10-11 (nothing pushed)
Private on GitHub: axis-bridge, nexxus, axis-core, picthis, theblogguyengine, theblogguy (all six `PRIVATE`). Unpushed commits: main 56, nexxus 18, axis-core 7, picthis 7, theblogguyengine 1,
theblogguy 0. gitleaks is not installed, so I ran a pattern scan over the added lines of every unpushed commit in the five repos that have any (about 49,000 lines): clean apart from two test
fixtures that are not secrets (the string `-----BEGIN RSA PRIVATE KEY-----` used as a detection test input, and a unit-test constant). Installing gitleaks and scanning the full history is still
the better check before the first push. picthis has an untracked `Nexus/` folder (auto-created scaffolding from importing a NEXXUS module from that directory; not part of the repo).

## Updated 2026-10-12
* **The axis gate is re-sealed** (`python -m axis_gate seal core`, then `verify`: "nothing drifted"; naming audit CLEAN; 131/131 gate tests). Every "not re-sealed: your call" note above is now settled.
  `python verify_all.py` can say ALL GREEN again once the sealed files stay put: **re-seal again after any further edit to a sealed core file** (the dashboard page and the portals are not sealed).
* **`restart_nexxus.bat` now starts the four domain hubs** after the server (it clears stale ones on their ports first, python processes only, then checks each `/health`). That file is git-ignored
  (it is your local startup file), so the change stays on this machine. The earlier warning that the hubs do not survive a restart no longer applies.
* **No mock data anywhere.** `portal_data/` ships no data (the seven sample files are deleted; `hub_catalog.json`, a real list of real tools, is the only tracked file there; your real data files are
  git-ignored). The page's invented dashboard hubs, per-utility parameters, wave animation and hard-coded Settings claims are gone; hub prompts carry the live state. Details: `PORTALS.md`.
  `portal_fixtures.py` is test support only and writes to a temp folder.
* **Home-screen fixes** in the dashboard page: home-only elements stay on the home room, the Link > Engines tab redraws every time, the mode menu is our own stable list, the status pill shows only
  while NEXXUS works, response cards carry NEXXUS branding. All pinned by `test_ui_state.py`.
* **Another session is editing the same working tree** (an "Engine desks" window: `desk_bridge.py`, `/api/desk/*` routes in `python_server.py`, desk UI and tests in the page). `desk_bridge.py` is
  git-ignored by the `*_bridge*.py` privacy rule, so it will not be pushed; `python_server.py` imports it inside a try/except. Its edits are in the same files as mine, so my commits include them.
  Look at that work on its own before the first push.
* picthis is clean (the stray `Nexus/` scaffolding folder was deleted; it is re-created whenever a NEXXUS module is imported from that directory, so delete it again if it returns).

## Going public later (not now)
Do NOT flip this repo to Public. Instead make a new repo from a clean copy: the starter pack only (the bridges you pick, using the `!path` lines in
`.gitignore` or `git add -f`), plus `PRIVATE_MODULES.md`, with fresh history. Keep this repo as the private full backup.

## Secret scan results (gitleaks 8.30.1, full history, 2026-10-12)
- axis-bridge: 4 findings, all false positives (test dummies such as `hunter2-body`, a test string `abcdefgh1234`, and a function call named `read_staging`).
- picthis, axis-core: clean. TheBlogGuyEngine: 1 false positive (`sk_test_` dummy in `test_nexxus_surface.py`).
- **nexxus: 1 REAL finding.** A Google AI API key is hard-coded in the first commit of `processor.py` (commit `1f91069`, "Create processor.py"), and that commit is already on GitHub (the repo is
  Private). The current file no longer contains it. **Rotate it**: revoke the key in Google AI Studio / Google Cloud console (Credentials) and make a new one if you still need it; once revoked
  it is harmless even though it stays in history. Rewriting history is optional and is not needed after revoking.
