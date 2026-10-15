# NEXXUS Definition of Done (the A+ bar)

Anything new (an engine, a module, a dashboard, a route) counts as DONE only when all nine pass (item 9 was added after test runs polluted live inboxes on 2026-10-13).
Paste the raw proof into the validation chat. A summary is not proof.

| # | Requirement | How to prove it (raw output) |
|---|---|---|
| 1 | **Real health check.** It tests something the component truly depends on, never `return {"ok": True}`. | Run `echo {"op":"health"}\| python <file> --mesh`. Then break a dependency (wrong hub address, no secret) and show it reports `ok: false`. |
| 2 | **Failure tested, not only success.** Wrong secret, hub down, dependency missing: it fails safely with a plain message. | Paste the `SECURITY ALERT` line and the 401 for a wrong secret. Paste the plain-words message when the dependency is down. |
| 3 | **Isolation.** If it dies, nothing else stops. | Close its window. Show the other components still LIVE. |
| 4 | **Visible state.** The dashboard shows LIVE, stale/NO HEARTBEAT or down within a known time. | Time how long NO HEARTBEAT takes to appear (current: about 24 s). |
| 5 | **Handles messages.** It does something with `message` and `instruct`. | Send it a message from another engine. Show `received: true` and the reply, or its inbox. |
| 6 | **No leaks.** No exception text, file paths or keys in anything a user sees. Keys only from environment variables. | Trigger an error from the chat/dashboard and paste what the user sees. Search the file for keys. |
| 7 | **Part of the cluster, no orphans.** Engines are a headless background mesh; they need no dashboard card of their own. Bots, profiles and vault items still must be nested on a dashboard. An engine orphan is a dead process or an unreferenced file/folder, never a healthy engine without a card. | `GET /api/dashboards/audit`: `ok`, no orphans, and `engine_cluster.ok` with the engine live and not in `dead_processes` / `unreferenced_folders`. |
| 9 | **Tests leave nothing behind.** Tests and checklist runs write to a temp folder, never into real engine folders, logs or inboxes. | Before and after a full run, list the engine folders: 0 new files. |
| 8 | **Evidence on file.** A test, a dated raw log, a commit. | `git log -1 --stat`, the test file name and its pass count, the log path. |

## Grades
- **B**: runs and heartbeats, but proof is mostly "it works" or the health check is a stub.
- **B+**: items 1-4 proven on the live system.
- **A-**: 1-6 proven, plus remote access and any hardware path tested for real.
- **A**: 1-7 proven with raw logs.
- **A+**: all 9, and a new component passes the same bar the first time without rework.

## How to use the template
1. Copy `engine_entry_template.py` into the engine's entry file. Set `ENGINE_NAME` to its exact mesh name.
2. Replace the TODO health check in `mesh_handle` with a real one.
3. To act on messages, define `on_message(sender, payload)` ABOVE the mesh snippet (below it, the hub's `--mesh` call exits before it is read).
4. Register jobs with `@utility(...)`, also above the `--mesh` block.
5. Put `nexxus_governance.py` where the engine can import it and set `NEXXUS_GOVERNANCE_SECRET` to the same value as the server.

## Notes added in this repository (2026-10-13)
- `python engine_checklist.py <engine> [--stop-test]` or `--all` runs all nine items and writes the raw output to `logs\engine_checklist_<engine>_<date>.txt`; an item it did not exercise says NOT RUN, and item 8 says BLOCKED while commits are on hold.
- `engine_entry_template.py` (in the nexxus folder) is the three snippets joined in order, kept identical to them by `test_entry_template.py`. Its health check is already real: step 2 only applies if the engine has its own dependencies to add to `_health_checks()`.
- Standard set by the owner 2026-10-13: the 21 engines are one headless background cluster (relay, persistence, ingestion); the dashboard is the command and aggregation layer (telemetry, perimeter, quarantine), not 21 widgets. `engine_cluster` in the audit rolls them up.
- New bots, profiles and vault items must be nested on a dashboard (`/api/dashboards/<hub>/nest`), otherwise item 7 fails: the audit lists them as orphans.
