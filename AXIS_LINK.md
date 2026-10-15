# AXIS LINK (Link mode)

The backend window into everything moving through NEXXUS. It exists in two places only: **Link mode** (bottom-left mode selector, "Mode: Link") and its own card in
**Settings**. It is separate from public storefronts such as PICTHIS: nothing here is exposed to them, and the contents need the admin token.

Read-only. It watches and explains; it never changes an engine, a file or a setting.

## What you see in Link mode

| Where | What |
|---|---|
| Left, **TRANSMISSION** (stays open while the mode is on) | The live transaction log, newest first. Filters: Chat / Modules / Mesh / Bus, and "Pings + heartbeats" (hidden by default, there are many). The **Layman / Terminal** switch translates every line. |
| Right, the flyout (same horizontal axis; only exists in Link mode) | **Inspector**, **Engines** and **Hypothesis desk** tabs. |
| Above the command prompt | The two input-queue lights. |
| Settings, "AXIS LINK" card | Mode, ledger numbers, queue numbers, a button to open Link mode. |

Leaving Link mode closes both panels. The Boiler Room (Diagnostic mode) and Transmission never show together.

## Inspector

Click a line in Transmission.

* **Route**: the message drawn node by node, with the time between nodes. Green went through, amber was refused, red failed. Blue diamonds are the points where it
  was checked (signature, timestamp, admin token, mode). The slowest gap is orange.
* **Timeline**: a scrubber and Play / Pause. Real times are often a few thousandths of a second, so Play is slowed to be watchable and says by how much; the numbers
  shown are always the real ones.
* **Terminal view**: header, hop table with times, checks, and the redacted bytes as a hex dump. **Layman view**: what it was, who and when, each step in plain
  English, what was verified, anything unusual.
* **Interrogate a part**: pick any element (sender, destination, a step, what was verified, how fast, how it ended) and press *Ask NEXXUS*. You get the **exact facts**
  immediately (computed from the record) and then NEXXUS's own words, written by the local model from those facts only. If the model is offline the facts stand alone.

## Hypothesis desk

Write an idea ("picthis is slow because the gateway is the bottleneck"). NEXXUS first **measures** it against the ledger with fixed rules and shows a verdict per claim:

| Claim | SUPPORTED when | Needs |
|---|---|---|
| slower than the rest | its median is over 1.5x everyone else's | 5+ transactions for that engine |
| fails more than the rest | its failure rate is 10+ points above the fleet's | 5+ transactions |
| carries most of the traffic | it is part of more than half of the recorded transactions | 10+ recorded |

Otherwise NOT SUPPORTED, or TOO LITTLE DATA. Then the model works through a fixed outline (restate, variables, evidence for and against, logic audit, a safe stress test,
verdict, one question back) using only those measurements, and you answer it: the loop continues until you start over.

## Flight Records (base of the Settings interface)

Every payload NEXXUS takes in (a chat, a mesh message, a module call, a bus order) is a **flight** with a Flight ID such as `FL-S8K3QZ-0042` (a time part that changes every
start plus a counter, so IDs are never reused). Settings > bottom card **Flight Records** lists them (filter: All / Problems only / Conversation / Tasks and traffic) and
**clicking one opens the trace**: a verdict (completed, refused, failed, in flight, stalled), the exact place it was refused / failed / is stuck, the reasoning, what to do, and a
table of every checkpoint with its time, the gap before it, whether a check passed, and the result. The slowest gap is shaded.

* A chat is opened in the ledger the moment the input is taken in, so while the model is still working it shows as **IN FLIGHT** with the last checkpoint it cleared; after 30 s
  with no result it is **STALLED** and the trace says it has not moved past that checkpoint.
* The reasoning comes from fixed rules over the recorded checkpoints (a failed signature, a wrong token, a mode hold, a Hard Lock, a module that did not answer, a module that
  returned HTTP 401 / 5xx, a full input queue). When the record does not say why, the trace says exactly that instead of guessing.
* Lookup works by transaction id or Flight ID: `GET /api/link/txn/<id or FL-...>` (admin token) returns the trace under `diagnosis`.
* Server-route checkpoints are stamped on arrival and at the end (that is what is measured); module calls carry real send and answer times.

## JSON that leaves the machine is strict (image and model rendering fix)

Python writes `NaN` / `Infinity` for a float that came out that way and cannot write numpy numbers, Paths or sets; the browser's `response.json()` rejects those words, so one such
value anywhere in a generation result broke the picture / model display. PICTHIS also read its worker's result with a bare `json.loads`, so any output after the result line raised
an error that the HTTP handler reported as a 400 "bad request" for a job that had actually finished. Now:

* `picthis/backend/safe_json.py` makes every reply strictly valid (NaN / Infinity become null, numpy / Path / bytes / sets become plain values) and reads the worker's result
  tolerantly; an unreadable result is a 502 "finished, but its result could not be read" with the reason, a malformed request body is a 400 that says so.
* The PICTHIS page reads every reply through `readJson`, which turns stray NaN into null and otherwise says what arrived ("not valid JSON (HTTP 502, text/html): ...") instead of
  "Unexpected token < in JSON"; the produce and chat calls no longer swallow a bad reply into an empty object.
* The NEXXUS server's JSON provider applies the same NaN / Infinity rule to every reply.

## Two-slot input queue

Messages to NEXXUS (`/command-dispatch` and `/bridge`) are answered **one at a time, in the order sent**. The line holds **two** in total: the one being answered and
one waiting. A third is **refused at once** with HTTP 429 ("maxed out"); nothing is queued or dropped silently, the lights above the prompt turn red, and the turned-away
count is kept. A slot frees the moment its answer is done. Lights: dark/green idle, amber processing, red both slots busy.

## What is recorded

An in-memory ledger of the newest 600 transactions (cleared on restart):

* signed calls to connected modules, timed for real by `nexxus_external` (built, sent to the gateway, answered; the gateway and the module cannot be separated, and the view says so);
* mesh messages, heartbeats, instructions, utility calls and jobs, and orchestrator bus orders;
* every chat, with the queue wait and the mode-gate decision.

Timing honesty: on server routes the arrival and the checks are stamped at arrival and the handling at the end, because that is what was measured. Anything not measured
is not drawn.

Secrets are blanked before anything is stored: keys containing `secret`, `token`, `password`, `credential`, `signature`, `apikey`, `authorization`, `cookie`, `private`,
or ending `_key`. The tests assert none of the throwaway secrets appear in any view.

## Routes (all but the queue state need `X-Nexxus-Admin-Token`)

`GET /api/link/log`, `GET /api/link/txn/<id>`, `POST /api/link/analyze`, `POST /api/link/hypothesis`, `GET /api/link/job/<id>`, and the open `GET /api/input/queue`.

## Files

`nexxus/link_hub.py` (ledger, redaction, hex dump), `nexxus/link_translate.py` (two voices, touchpoints), `nexxus/link_analyst.py` (hypothesis evidence),
`nexxus/input_queue.py` (two slots), server section "AXIS LINK" in `python_server.py`, hook `TXN_HOOK` in `nexxus_external.py`, mode `link` in `nexxus/mode_policy.py`,
panels in `render/babylon_preview.html`. Tests: `nexxus/test_link_hub.py`, `test_link_routes.py`, `test_ui_state.py`.

The server must be restarted for any of this to appear; reload the page afterwards (Ctrl+F5).
