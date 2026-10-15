# The four portals

The dock reads **Sports, Markets, Logistics, Economics, Home, Link, Build** (Perimeter stays at the far end). Each portal is a glass dropdown anchored under the strip. The page only draws and
asks; every calculation runs in `axis-logic` (`portal_worker.py`) in a throwaway process with a 25-second limit, and reaches the page through the NEXXUS bridge (`portals.py`, routes under
`/api/portals`). Heavy maths and engine logic never run in the browser.

| Portal | Tabs | Compute (axis-logic) |
|---|---|---|
| Sports | Broadcast, Edge, Players, Teams, Parlay | `SportsEngine`, Elo, implied odds, Kelly (capped), parlay pricing, player queries |
| Markets | Probability, Forecast | `StocksEngine`, bootstrap price cone |
| Logistics | Cockpit, Inventory, Queue, Delivery | stockout risk, EOQ, reorder point, Erlang C queue, on-time rate and significance test |
| Economics | Macro, Modeling | `lib/economics.py`: trend with a bootstrap range, CAGR, real rate, savings, NPV/IRR, loans, inflation restatement |

## What it will not do

Nothing places a bet, trades, orders or ships anything. The portals' calculators make no outside network calls (the only outside call anywhere in the hubs is a chat's `search:`, below). Results are
estimates with their uncertainty (a small sample cannot look confident).

## Data: real or nothing

NEXXUS ships **no data**: no sample rows, no example numbers, no placeholder templates. `portal_data/` holds only `hub_catalog.json` (a real list of real tools, flagged as editorial). Every
calculator input starts blank, and nothing runs on invented values. The portals work on **your** data sets, each a file `portal_data/<name>.json` (`ticker`, `players`, `teams`, `legs`, `series`,
`assets`, `macro`; the real ones are git-ignored) that must:
* follow the schema in `portal_schemas.py` (`python -c "import portal_schemas as s; print(s.describe('teams'))"` prints it; the page shows it too),
* name where it came from in `source` (provenance is mandatory),
* not be sample, placeholder, demo or mock data: a file marked `"sample": true`, or whose source or names say sample, placeholder, demo, mock, fake, dummy, lorem or example, is **rejected**.

A data set is therefore in one of three states, and the page, the hub chats and every hub's prompt report exactly that: **loaded** (rows and source shown), **not loaded** (a card with the schema and an
import box: paste your JSON, it is validated and saved with the admin token, nothing is stored unless the whole file is valid), or **rejected** (the reasons are listed and none of the file is used).
The same rule governs the rest of the dashboard: the dashboard hubs list is empty until a real dashboard exists, the Engine Diagnostic cards show only the utilities an engine has actually declared
to the mesh, and the Settings readouts (server file, uptime, memory, perimeter, axis gate) are measured from the server.

## Live state in every hub prompt

Each hub chat's system prompt ends with a block read from the system on every turn (`portals.state()` through `portal_schemas.prompt_block()`): which data sets are loaded with their row counts and
sources, which are not loaded or rejected, the exact argument schema of every calculator in that hub, the size of its catalog, and the rule that follows: no data set means no figures, so the model
must say there is no data and never invent a score, price, rate, row, name or statistic. The model therefore reads the real state, never an example.

## Search and Add to Hub

Every portal has a search bar covering its whole field (all kinds: APIs, databases, calculators, feeds, platforms, libraries). The search runs in `axis-core` (`hub_search.py`) over
`portal_data/hub_catalog.json`, groups the matches by category, and marks the best rated in each. **That catalog is an editorial starting list written from general knowledge, not fetched
live.** Ratings are opinions; check each provider's terms, pricing, licence and availability in your jurisdiction. NEXXUS searches the catalog, not the internet: add an entry to the file and
it becomes findable (needs `id, portal, name, kind, category, rating, summary, tags`).

**Add to Hub** records the entry in `portal_data/hub_<portal>.json` and shows it in that portal's **My Hub** tab at once. Built-in calculators mount as working forms. Outside APIs and feeds
mount as connector cards marked *registered, not connected*: they stay inert until you wire a connector and key yourself. Only ids that exist in that portal's catalog can be mounted.

## Domain chats (one per hub, locked)

Each portal window has its own chat at the bottom. Every turn is gated three ways (`portal_chat.py`): a deterministic **input gate** (vocabulary scoring, clause by clause: no signal for this hub,
more signal for another hub, or another hub mixed in, is refused and the model is never called), a **hub-specific system prompt** (domain, a refusal marker, untrusted-data rule), and an
**output filter** (a reply that carries the marker or has drifted into another domain is dropped and never remembered). Messages with no vocabulary signal at all (an unknown athlete, a new
ticker) get a one-word verdict from the local model, which **fails closed**: anything but this hub's domain, junk, or a model error is a refusal. A short follow-up is judged with the previous
question as context, so "why is that?" works and "what about Rome?" does not. History is per hub, on the server, and is never written to the main chat session.

In a hub's chat, `search: <query>` runs this hub's catalog through axis-core and a web search through the axis search engine, and `data: <name>` reads this hub's own data files. The query must
pass the gate; web snippets are untrusted: stripped of markup, cut to 300 characters, dropped if they look like instructions, and kept only if they score inside **this** hub's domain. Web search
sends only the query text to DuckDuckGo; set `NEXXUS_PORTAL_WEB_SEARCH=0` to switch it off.

Known limits, measured not assumed: the vocabulary gate has no false leaks on the test sets, but a pure keyword gate refused about a third of fresh, legitimate questions until the vocabulary was
widened and the model fallback added; the model fallback is only as good as a small local model. Strictness has a cost: a question that touches two hubs is refused, not half-answered.

## Home screen courier (domain dispatch)

In Conversation mode, a home-screen prompt that clearly targets **exactly one** hub is not answered by NEXXUS. `domain_dispatch.py` packages it and POSTs it over loopback HTTP to that hub's own
port, and the hub's reply comes back **unaltered** (the reply text byte for byte; the hub's whole JSON beside it as `hub_payload`). Anything else (general tasks, build and command prompts, mixed or
ambiguous prompts, any other mode) takes the regular route. The courier uses no model, so it has no system prompt: it is deterministic. If a hub is down it says so and **does not** answer in its
place.

| Variable | Default | Meaning |
|---|---|---|
| `NEXXUS_PORT_SPORTS` / `_MARKETS` / `_LOGISTICS` / `_ECONOMICS` | 8721 / 8722 / 8723 / 8724 | placeholder: each hub's local port |
| `NEXXUS_DOMAIN_HOST` | 127.0.0.1 | loopback only (`localhost`, `::1`); any other host is refused |
| `NEXXUS_DOMAIN_TIMEOUT` | 600 | seconds a hub may take (a cold local model is slow) |
| `NEXXUS_DOMAIN_DISPATCH` | 1 | `0` switches the courier off |

`restart_nexxus.bat` starts the four hubs after the server (it first clears stale ones on their ports, python processes only, and checks each hub's `/health`); `start_domain_hubs.bat` starts just the hubs
(each is `python domain_hub_server.py <domain>`, serves only its own domain and refuses any other). `GET /api/portals/dispatch` shows the settings and
which hubs are up; `POST /api/portals/dispatch/preview {"message": ...}` says where a prompt would go without sending it. Note that a hub call holds one of the home screen's two input slots while it waits.

## Windows

The portal dropdown and the Perimeter panel are real windows. **Drag** by the header; **resize** from the corner grip (double-click the grip to put the window back); **Expand** (⤢, or double-click
the header) fills the screen and **Esc** restores it before anything is closed; **Minimise** (–) folds it to its header; **Close** hides it. Position and size are remembered per window. Moving,
sizing or minimising only changes geometry: the Perimeter poll, the portal calls and the telemetry loops keep running underneath.

## Top bar

Three slots under `justify-content: space-between`: Python server status on the left; search and the tool buttons in the middle; engine LEDs, beep, notifications and Auto Save on the right, ending
just before the dock. The space the dock needs is measured live (`--dock-w`), not hard-coded. Portal buttons show icons only below 1700 px wide, and the Auto Save text folds to a dot below 1500 px.

## Tests

`python test_portals.py` (worker maths, catalog integrity, search, mounting, routes, strict dock order, no-innerHTML rule, no network imports on the compute side).
