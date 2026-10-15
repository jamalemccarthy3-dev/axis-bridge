# Upper-right control dock, Perimeter and the token dialog

## The dock (top-right of every screen)

| Button | What it does |
|---|---|
| **LINK** | Switches Link mode on or off (Transmission log on the left, engine hub on the right). Lit while Link mode is on. See `AXIS_LINK.md`. |
| **BUILD** | Opens the **Build Mode silo**: the same Build Mode box as the home screen side panel, moved into the dock (the side panel leaves a "Bring it back here" note while it is away). **Expand** takes the silo over the whole screen for backend observation; **Unexpand** (or Esc) returns it to the dock. Closing the dock puts it back in its home slot. The box's own pop-out button does the same Expand/Unexpand while it is docked. |
| **PERIMETER** | The Perimeter Gate with the Triad Protocol board beneath it (below). Flashes red on a breach. |
| **HOME** | Closes the dock panels, puts Build Mode back, and returns to the home screen. |

## Perimeter Gate (upper)

The existing axis gate, shown live: whether every sealed manifest still matches, how many inbound items were allowed / blocked / cleared by you, and the overrides in force.
It does not approve anything: inbound files and builds stay staged until you sign them off yourself (Settings > axis gate, tool briefings). **Verify manifests now** runs the gate's own check (admin token).

## Triad Protocol (beneath it)

A live board of every node (the 21 mesh engines, the connected modules and anything that shows up in traffic): status and latency from the engine telemetry, packets sent / received / failed
from the AXIS LINK ledger, the newest outbound journeys, and your overrides:

* **Hard Lock** (press twice to confirm). While a node is locked, NEXXUS refuses everything from it or addressed to it on the mesh (HTTP 423, recorded in the ledger as refused) and stops
  calling it as a module. It is enforced here, in NEXXUS's own server and bridge: it changes nothing inside the engine and kills no process. **Unlock** lifts it. The lock survives a restart.
  The Triad module's own `lockdown.flag` needs its master secret and is deliberately not touched.
* **Quarantine** keeps a redacted, inert copy of the node's newest recorded packet. A packet whose signature fails is quarantined automatically. Copies are text only: never executed,
  imported or replayed. **Inspect** reads one, **Release** deletes it.

All overrides need the admin token. The list of nodes, packets and quarantine contents is admin-gated; only counts are public.

## Breach and notification loop

A breach is: a signature that did not verify, a wrong admin token on the mesh or bus routes, a module refusing a signed request, or a Hard Locked node trying to talk.
Each raises (repeats within 5 seconds count once):

1. a red flash on the PERIMETER button and panel, and a banner across the top;
2. one entry in the notification bell with an **Open command center** action;
3. a browser notification only if you already allowed them for this page (it is never requested automatically).

**Open command center** (banner or bell) focuses the window, goes to the home screen and opens the Perimeter panel. **Acknowledge** stops the flash. Your own Hard Lock is logged
and notified but does not flash.

## The AXIS Link key fix

Entering the admin token used `window.prompt`, which embedded browsers (including the Claude app's pane) refuse: it throws "prompt() is not supported", so the key sequence never
completed and stayed locked. It is replaced by an in-page dialog (`#tokDialog`): Enter submits, Esc cancels, the token is **checked with the server** (`GET /api/auth/check`) before it is
kept, and a wrong token or an offline server says so instead of freezing. The token stays in this tab only. After unlocking, repeat the action you started.

## Routes (all except `/api/perimeter/status` need `X-Nexxus-Admin-Token`)

`GET /api/auth/check`, `GET /api/perimeter/status`, `GET /api/perimeter/triad`, `POST /api/perimeter/lock`, `POST /api/perimeter/unlock`, `GET|POST /api/perimeter/quarantine`,
`GET|DELETE /api/perimeter/quarantine/<id>`, `POST /api/perimeter/ack`.

State is kept in `perimeter_state/` (git-ignored). Files: `perimeter.py`, the "PERIMETER" section of `python_server.py`, `BLOCK_CHECK` in `nexxus_external.py`, the dock in
`render/babylon_preview.html`. Tests: `test_perimeter.py`, `test_ui_state.py`.

Restart the server and press Ctrl+F5 to load it.
