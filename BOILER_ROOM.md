# Diagnostic Mode: the Boiler Room

A live monitor of the whole machine on the left, and a conversation with NEXXUS that is **locked to the system**. Local, standard library only, tested.

## The widget and the panel
* The **Boiler Room widget** sits at the top of the left sidebar: one light per engine, a one-line summary (modules answering, mesh heartbeating, CPU, memory) and two small bars.
  It is always there and updates by itself.
* **Click it** and the **Boiler Room panel** takes over the left-hand side of the screen. It opens already showing live data (no command to type) and refreshes every 2 seconds:
  * **KPIs:** CPU, memory, disk, server uptime, threads.
  * **Bridge:** the NEXXUS server, gateway (8080) and Ollama ports (open/closed), modules answering/linked/link-failing, mesh map version and how many engines are found, ready and heartbeating.
  * **Services:** the local model server (installed and loaded models), the job queue, the axis gate (sealed, drift) and the ledger chains.
  * **Engines**, in three honest groups: *modules* run by the gateway (PICTHIS, the blog, your new engines), *engine builds* in progress, and the 21 *mesh engines* (heartbeat, stale, no heartbeat, missing). Each row has its light, state, latency, a sparkline of recent pings and the time of its last event.
  * **Live events:** the same numbered feed that flashes the header lights.
* **Click any engine** to drill down: a larger latency chart and status strip, its facts, the **utilities it really declares** (asked over the signed bridge for linked modules; read-only vs build is shown), mesh heartbeat metrics, mesh messages and its own events. *Ping now* and *Ask NEXXUS about it* are there too. *All engines* goes back.
* Nothing in the panel changes anything. Where a source is missing it says *unavailable* instead of showing a made-up number.

## The locked conversation (Mode: Diagnostic)
Pick **Mode: Diagnostic (Boiler Room)**. The panel opens by itself, and the conversation is locked to the system, the engines and the infrastructure:
* A message that is not about them (a joke, the weather, small talk) is **not answered**; NEXXUS says why and offers *Leave Diagnostic mode* or *Stay*.
* A system question is answered **from the live data** (status, what is offline, one engine's state, CPU/memory, bridge and ports, jobs, gate, models, recent events), instantly and exactly.
  If the data cannot answer it exactly, the model answers with the live facts in front of it and an instruction to stay on the machinery.
* Build orders are still refused (this mode talks and audits; it does not build).

## Honest limits
* The topic lock is a **word-based filter**, not understanding. It errs toward blocking small talk, so a legitimate question with none of the system words may be turned away
  (one click leaves the mode). The server enforces it, not just the page.
* The model fallback is told to stay on the system, but a small local model can still wander; the data-grounded answers cannot.
* A mesh engine shows *no heartbeat* until it really sends one; today none do, and the panel says so rather than painting them green.
* Memory and CPU come from `psutil`; without it those two fields say *unavailable*.
