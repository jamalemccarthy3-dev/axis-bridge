# Explicit naming, adoption, and the read-only commercial watch

## 1. Explicit naming (`nexxus/naming.py`)

Everything NEXXUS generates is named for what it **is**, taken from the request that made it. These stand-ins are refused: *untitled, unnamed, default, new, temp, test, output,
result, file, document, item, thing, stuff, asset, project, build, drop, copy, final, index, app*, a generic word with a number on it (`file1`, `tmp123`), bare numbers and stamps,
and anonymous tokens (`a3f9c2d1`). A name made only of those is not a name.

* When a name can be worked out from the request ("a red fox logo for Bakery Co" -> `red-fox-bakery-co-logo`) it is. When it cannot, the job is refused with "say what it is in a few
  words". Nothing is invented.
* **Creations**: the folder is `cr_<what-it-is>_<date>_<time>` (a counter if made twice in one second, never a random token), the file is `<what-it-is>.svg` / `.html` instead of
  `graphic.svg` / `index.html`, the title comes from the request. Older creations keep their ids.
* **Engine builds**: the engine is named from what it does (`counts_words`), never `engine` / `engine_x`; a stand-in name you pass is rejected.
* **Vault drops** (`nexxus_talks`): the drop is named from its name, asset id, source folder or request; with none of those, the stage reports an error instead of filing it as
  "Untitled Drop".
* **PICTHIS**: a job is named from its objective (`red-dragon-flying-castle-video`); `Untitled_Build` and the page's `<mode>_Build` / `<mode>_Video` labels are gone, and a request
  that says nothing is refused.
* A source scan (`test_naming_watch.py`) fails if a stand-in label ever reappears in the generating code.

**Adoption.** Every generated folder gets a `.nexxus_tag.json` when it is created: its name, kind, who made it, the request, and every file with size and SHA-256. That is how a
component is welcomed into its place rather than orphaned. Settings > Perimeter shows how many folders have no tag; **Tag the untagged** adds tags to older ones (creations,
deployed engines). It never renames or moves anything. `GET /api/naming/audit`, `POST /api/naming/adopt` (admin token).

Deployed engines keep their explicit names in the UI directory. The internal engine-build *staging* folders are still named by build id; they are working space, and each holds a
`build.json` that names the engine.

## 2. Read-only commercial watch (`nexxus/vital_watch.py`)

NEXXUS may **check the pulse** of commercial-grade files and may never touch them.

* **You** decide what is watched, by hand-editing `commercial_watch.json` in the repo root (git-ignored):
  `{"watch": [{"name": "storefront-core", "path": "C:/path/to/storefront", "health_url": "http://127.0.0.1:9000/health"}]}`
  (`health_url` is optional and must be a loopback address; it is only ever a GET.) No route and no code path adds, edits or removes an entry.
* **Pulse**: each path is opened read-only and streamed through SHA-256. Status: **breathing** (present, readable, same as the baseline), **changed** (differs; nothing was altered by
  NEXXUS), **missing**, **unreadable**, **not-answering** (files fine but the health URL did not answer), **new** (first sight: baseline recorded). The baseline lives in
  NEXXUS's own state file (`perimeter_state/vital_baseline.json`), never in the watched folder. Trees larger than 400 MB are fingerprinted by size and time for the largest files, and say so.
* **Boundary**: `guard_write` refuses any NEXXUS write inside a watched path (creations vault, engine deploy, tool staging all call it) and `guard_integrate` refuses to make a watched
  path, or a folder containing one, a tool or a module (tool approval and the module roster call it). A watched folder in the module roster is dropped, so it is never callable.
* A watched path going missing / unreadable / not answering raises an alert-level Perimeter event (flash + notification); a change raises a warning. **Accept new state** (admin token)
  records your edit as the new baseline; it writes NEXXUS's own state file only.
* Routes: `GET /api/vital/status` (bare counts, no names), `GET /api/vital/pulse` and `POST /api/vital/accept` (admin token). The Perimeter panel shows the list.

Tests: `test_naming_watch.py` (including that the watched files' bytes, sizes and modification times and the folder listing are identical after pulses).
