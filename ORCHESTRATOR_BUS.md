# Orchestrator bus: how NEXXUS and the engines work together without cheating on quality

NEXXUS already has a **mesh** (signed heartbeats, engine messages). What was missing is a rulebook for **build orders and quality control**.
`orchestrator_bus.py` is that rulebook plus a tamper-evident record. It is free, local, standard library only.

## The rules (all enforced in code, all tested in `test_orchestrator_bus.py`)
1. **Only orchestrators are addressable.** An order for a silo, or for an engine with no registered orchestrator, is refused. A silo cannot speak to NEXXUS.
2. **Every message is a signed envelope** (HMAC-SHA256, fresh timestamp, single use). Forged, changed, stale and replayed messages are refused.
3. **Fixed states, none can be skipped:** `ORDERED -> ACKED -> BUILT -> QC_PASSED -> ACCEPTED` (a failed QC sends the order back to `ACKED`).
4. **Independent quality control.** The verdict must come from a registered reviewer engine that is **not the builder**. A pass must name the SHA-256 of the exact built artifact, and cannot carry a critical finding.
5. **Only NEXXUS accepts.** At accept time the artifact is hashed again; if it changed after QC, it is refused. NEXXUS's own checks (`bus.nexxus_checks`) run too, so an engine saying "done" is never enough.
6. **Append-only, hash-chained ledger** (`logs/orchestrator_ledger.jsonl` when wired). Any edited, removed or reordered entry is detected, and a tampered ledger refuses to load.

## Using it
```python
from orchestrator_bus import OrchestratorBus
bus = OrchestratorBus("logs/orchestrator_ledger.jsonl")          # needs NEXXUS_GOVERNANCE_SECRET
bus.register_orchestrator("axis-video_creator", "video_creator.governor")
bus.register_orchestrator("axis-validator", "validator.governor", qc_reviewer=True)
order = bus.send_order("axis-video_creator", "video_creator.governor", {"make": "intro"})
# the engine's orchestrator replies with signed envelopes: bus.receive(env) for kinds ack, built, qc
bus.accept(order["id"])                                          # only NEXXUS can do this
```

## Honest limits
- It is the rulebook and the record. It is **not yet connected** to the server routes or to each engine's governor: those need a small client that sends the envelopes. That wiring is the next step.
- Anyone who holds `NEXXUS_GOVERNANCE_SECRET` can sign as any orchestrator (the same limit the mesh has). It protects against mistakes, silos and anything without the key, not against someone who already controls the machine.
- It decides *whether the process was followed*. How good the QC is depends on the reviewer engine's own checks.
