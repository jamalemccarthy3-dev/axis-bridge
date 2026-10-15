# Modules: drop in, take out

Everything in `axis-ui-interface/` that is a **module** is its own independent package: its own server, data and secrets.
The **gateway** (this folder, port 8080) is the shared front door, and **NEXXUS** is the watchdog neighbour: it can see each
module and ask it (read-only) for help, but it never runs a module's code and a module never needs NEXXUS to work.

## Add a module
Put a folder in `axis-ui-interface/` containing a `module.json`. Within ~10 seconds the gateway starts it, routes
`http://<its hostname>:8080/` to it, lists it on `http://localhost:8080/`, and (if it has a `nexxus` block) publishes it to NEXXUS.
No other file needs editing.

```json
{
  "name": "myapp",
  "type": "app",
  "hostnames": ["myapp.localhost"],
  "port": 8720,
  "start": { "cmd": ["{python}", "-u", "server.py"] },
  "health": "/api/health",
  "keep_running": true,
  "private_paths": ["/api/nexxus/"],
  "nexxus": { "path": "/api/nexxus/rpc", "secret_file": "nexxus.secret" }
}
```
Optional: `webhook_port` + `webhook_paths`, `wake_timeout`, `idle_minutes` (rest when idle), `proxy_timeout` (seconds to wait for a reply, default 60, max 3600; for modules that run long jobs), `note`.
Static pages: `"type": "static"`, `root`, `index`, and an allow-list (`files`, `prefixes`).

Rules the gateway enforces (a module that breaks one is reported on the launcher page and skipped; the others keep working):
- `start.cmd` must begin with `{python}` or `node`; the working folder and the secret file must be inside the module folder.
- Ports 1024-65535, never the bridge port 8000, and not shared with another module; hostnames must be unique.
- The NEXXUS secret is a file named `nexxus.secret` (32+ characters) in the module folder, shared with nobody else.
- Dropped-in modules start automatically, so only put folders here that you trust.

## Keys page: one place to enter every module's keys
`http://keys.localhost:8080/` (this computer only) lists the settings each module asks for and saves what you paste straight into that
module's own `.env`. It never shows a saved secret and keeps no copy. A module opts in by declaring what it needs in its `module.json`:

```json
"title": "My App",
"keys": [{ "name": "MYAPP_API_KEY", "label": "My API key", "help": "Where to get it", "prefix": ["sk-"], "secret": true, "restart": true, "group": "Section" }]
```
`name` must be UPPER_CASE; `prefix` (optional) rejects obviously wrong keys; `secret: false` shows the current value (for things like a mail host);
`restart: true` offers a Restart button because the module only reads `.env` at startup. Remove the module and its keys leave the page; delete the `keys/`
folder and every module still works.

## Remove a module
Delete its `module.json` (or its `<name>.module.json` pointer file in the UI root). The gateway stops the process it started, drops the
route and removes it from NEXXUS's list. Then the folder is free to delete or move. (Windows will not let you delete a folder
while a program runs inside it, which is why you remove the file first.)

## Connect a module that lives elsewhere (the normal way)
A module does not have to be inside `axis-ui-interface/`. Put a one-line file `axis-ui-interface/<name>.module.json` that points at its folder:

```json
{ "folder": "C:/path/to/your/picthis" }
```

The folder keeps its own `module.json`, data and `nexxus.secret`. The gateway treats it exactly like a module dropped in the UI folder:
it starts it, routes its hostname on port 8080, lists it on the launcher and publishes it to NEXXUS. NEXXUS cannot tell the difference,
because it only reads the roster (`axis-bridge/external_modules.json`) and the secret path listed there.

- **Connect:** create the pointer file. **Disconnect:** delete it. The module's folder is never touched.
- Moving the folder into `axis-ui-interface/` is optional and only a matter of tidiness. If you do, delete the pointer.
- Today: `blog.module.json` -> `Desktop/TheBlogGuyEngine`, `picthis.module.json` -> `Desktop/picthis`.

## What NEXXUS can do with a module
Only what the module declares as utilities, and the blog and PICTHIS declare just `status` and `health` (read-only). Every request is
signed with that module's own secret, valid once for 60 seconds, and only accepted from this computer through the gateway's
`private_paths` rule (requests arriving through a tunnel or proxy get a 404).

Run `python gateway.py --check` to see what would be discovered.

## Automatic ports (no port to choose)
Write `"port": "auto"` (and `"webhook_port": "auto"` if the module has a webhook listener) and the gateway picks a free port in
18000-18999, never one that any module declares as fixed, and remembers it in `auto_ports.json` so the module keeps the same port
after a restart. The module learns its port from the environment variables `NEXXUS_MODULE_PORT` (and `NEXXUS_MODULE_WEBHOOK_PORT`,
`NEXXUS_MODULE_NAME`), or you can put `{port}` / `{webhook_port}` in `start.cmd` or in `start.env` values:

```json
"port": "auto",
"start": { "cmd": ["{python}", "-u", "server.py", "--port", "{port}"], "env": { "MYAPP_PORT": "{port}" } }
```
Fixed ports still work exactly as before (PICTHIS 8710, the blog 8765/8766 and its tunnel are unchanged).

## NEXXUS through the same front door
`http://nexxus.localhost:8080/` reaches the NEXXUS dashboard and API (port 8000). This route is **local only and cannot be switched off that
way**: a request that carries any tunnel / proxy sign (X-Forwarded-*, CF-*, Tailscale-User-*, ...) or comes from another machine gets the same
plain 404 as an unknown host, and a cross-site POST is refused. Because the Blog Guy's webhooks reach this gateway through a public tunnel,
that rule is what keeps NEXXUS's admin functions off the internet. `ports.json` -> `"bridge"`. Modules still can never be routed to port 8000.

## Private traffic log
`logs/bus_private.jsonl` records every request and every start / stop / restart: when, which module, method, path, status, bytes, milliseconds,
and whether it looked like outside traffic. It never records request or response contents, headers, cookies or query *values* (only the
parameter names), and anything that looks like a token or long id in a path is written as `[id]`. It rotates at 5 MB. It lives in `logs/`, which
nothing serves.

## Watchdog
`run_gateway.bat` already restarts the gateway within 5 seconds if it stops. `../../nexxus_watchdog.ps1` (started at login by `nexxus_autostart.ps1`)
covers the rest: it checks ports 8080 and 8000 every 30 seconds, and after two misses in a row it starts what is missing (the gateway through its
own launcher; the NEXXUS server and any missing engine through the idempotent autostart). It never stops anything, gives up for 15 minutes if
something dies 5 times in 15 minutes, and writes to `../../logs/watchdog_private.log`.

## Settings > Modules, and the AXIS bridge
The NEXXUS dashboard (Settings face) lists every module with its state and a link; Wake / Rest need the admin token. The AXIS bridge understands
`modules` (list them) and `open module <name>`.
