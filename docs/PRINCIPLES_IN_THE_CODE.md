# Principles in the code

> **DRAFT for the owner's review. Not yet published.** Written from the code and tests as of 2026-10-14. Every row must still be true on the day this is released; re-check before publishing.

The [Core Philosophy](philosophy/CORE_PHILOSOPHY.md) and [AI Philosophy](philosophy/AI_PHILOSOPHY.md) are the blueprints NEXXUS started from. They were applied across the whole build, in large
and small pieces. This page points from each principle to where a reader can see it in the repository. It names areas and evidence only; it does not explain how any defence works.

**Built** = working and tested. **Partial** = some of it works. See [VISION_AND_STATUS.md](VISION_AND_STATUS.md) for what is still ahead.

## From the Core Philosophy

| Principle | Where to look | Evidence | Status |
|---|---|---|---|
| Sovereign Isolation | The engine folders `axis-ui-interface/project-X/silo_vault/axis-*` (21 independent engines) | [AUDIT.md](../AUDIT.md) section 3 (isolation measured on 3 of 21); item 3 of [QUALITY_CHECKLIST.md](../QUALITY_CHECKLIST.md) | Built |
| Interface Supremacy (the Universal Port) | The single mesh contract every engine answers; the checklist an engine must pass to count as done | [QUALITY_CHECKLIST.md](../QUALITY_CHECKLIST.md) and `engine_checklist.py` (nine items, raw output kept) | Built |
| Hardened Discipline | The `axis_gate` package: signed manifests, drift detection, replay protection | Gate suite in `verify_all.py`; [ARCHITECTURE_AUDIT.md](../ARCHITECTURE_AUDIT.md) section 5b | Built |
| Operational Stealth (Ghost Data) | Loopback-only by default; redaction and inert copies in `perimeter.py` | `test_perimeter.py`; [PERIMETER.md](../PERIMETER.md). Not yet tested against outside scanning | Partial |
| Administrative Sovereignty | Admin-token gating for every override; the sealed core | [PERIMETER.md](../PERIMETER.md); `axis_gate` | Partial |
| Systemic Integrity Protocol | Refusal and quarantine of failed packets, Hard Lock, and a recorded bulk release in `perimeter.py` | `test_perimeter.py` (16 tests). Fully automatic escalation to containment is not built | Partial |
| The Sovereign Agentic Fleet (muscles, tendons, brain) | Engines are the silos, the bridge connects them, the NEXXUS hub is the brain | README architecture table; [ORCHESTRATOR_BUS.md](../ORCHESTRATOR_BUS.md) | Built |
| R&D Incubation | A way of working, visible in the dated audit trail rather than in code | [AUDIT.md](../AUDIT.md) | n/a |

## From the AI Philosophy

| Principle | Where to look | Evidence | Status |
|---|---|---|---|
| Sovereign Architecture | As Sovereign Isolation above | As above | Built |
| The 90/10 Principle | Most of the repository is the hardening underneath: tests, signing, audit, checklists | `verify_all.py` runs 89 suites | Built |
| Rejection of Amnesia | Engine inboxes and liveness are kept on disk and survive a restart | [ARCHITECTURE_AUDIT.md](../ARCHITECTURE_AUDIT.md) section 5b. The local model's context window is small on modest hardware | Partial |
| Fact-Based Alignment | The audit states what is not proven as plainly as what is | [AUDIT.md](../AUDIT.md) sections 5 and 6 | Built |
| Faraday Bag | Software isolation: separate processes, signed calls, quarantine. It is not physical shielding | [AUDIT.md](../AUDIT.md) | Partial |
| Access Port | The signed, stateless way the hub calls an engine | `nexxus_governance.py`; [ARCHITECTURE_AUDIT.md](../ARCHITECTURE_AUDIT.md) section 1 | Built |
| Predictability Module | The probability engine in the `axis-logic` folder passes its own tests; its real-world accuracy has not been measured | Test output in `verify_all.py` | Partial |

## Notes for the owner (delete before publishing)

- Rows deliberately left out: nothing from the Third, Fifth or Diagnostic Isolation documents is mentioned here; they stay in `docs/no-view/`.
- `engine_checklist.py`, `QUALITY_CHECKLIST.md`, `AUDIT.md`, `ARCHITECTURE_AUDIT.md` and some tests are new this session and not yet committed; the links work once they are.
- If the private bridge modules stay gitignored, a reader following these links can see the evidence but not run the hub. Settle that before publishing.
