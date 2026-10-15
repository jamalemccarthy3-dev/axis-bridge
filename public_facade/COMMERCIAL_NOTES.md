# Industrial Build: commercial notes (PRIVATE; not part of the public output)

Not legal advice. Everything binding must be drafted or reviewed by a lawyer in your jurisdiction before the first sale.

## The model (as the owner defined it)

The free repository exists so that people **build it themselves**: learn, put in the reps, produce the product. The $10,000 Industrial Build is **not** a charge for raw files or for restricted third-party
models: it packages the owner's **time, engineering services and custom architecture** into a turnkey setup for those who choose not to build. The README sells it as a service ("the master architect's fee").

## What the service framing fixes, and what it does not

- FIXES: selling files or weights you do not own. You are selling work, and third-party components are "not sold, not relicensed" (stated in the README).
- DOES NOT FIX: the customer's own commercial-use rights. If the build you install runs on a model or library whose licence forbids commercial use, the customer is the one in breach and will come back to you.
  So the build you deliver must be CONFIGURED for components that are licensed for the customer's commercial purpose, and you must be able to show that.

## Third-party licence findings (checked on this machine, 2026-10-08)

| Component | Where | Licence (as reported) | What to do before selling |
|---|---|---|---|
| qwen2.5-coder:3b (the DEFAULT build model) | local Ollama | **Qwen Research License Agreement** | Research-style: likely restricts commercial use. Read the full text; do not deliver this as the default |
| nvdiffrast | PICTHIS 3D | **NVIDIA Source Code License (1-Way Commercial)** | Non-commercial for everyone but NVIDIA. Do not include in a delivered build without a licence |
| llama3.2, nexxus-ai (a Llama 3.2 derivative) | local Ollama | **Llama 3.2 Community License** | Commercial use allowed with conditions: attribution, licence and acceptable-use pass-through, naming rules for derivatives |
| phi4-mini | local Ollama | MIT | Fine |
| InstantMesh (code) | PICTHIS 3D | Apache-2.0 | Fine for the code; its model weights carry their own licences |
| Babylon.js 9.30.0 | dashboard | Apache-2.0 | Fine; notice kept in `render/vendor/THIRD_PARTY.md` |

## Open items

1. Licence audit (an SBOM with the licence of every component) and a commercially licensed default model for delivered builds. OPEN.
2. Fixed "penalties" can be void as penalties; the README uses tiered, proportionate consequences with liquidated damages as a genuine pre-estimate, in the agreement only. OPEN: counsel sets amounts.
3. An NDA is not a licence: ONE agreement carries both. Rely on contract and trade secret; AI-assisted code has weak copyright protection. OPEN: counsel.
4. Detection: per-delivery fingerprinting and audit rights are promised in the README. OPEN: BUILD the fingerprinting before the first sale (a unique marker per delivery).
5. Business-only sales, authorised signatory, e-signature records. Stated. OPEN: provider and record-keeping.
6. "Perpetual for the delivered version" keeps the "no lock-in" promise honest. DECISION FOR YOU: confirm.
7. "Industrial" claims need evidence. Do not promise SLAs, security guarantees or uptime you cannot back (`ARCHITECTURE.md` section 7 lists the known gaps). OPEN: scope the retainer (hours, response targets, exclusions) so one person can deliver it.
8. Remote support is customer-initiated. Stated.
9. The middle gap (consultants and agencies who cannot build and will not pay $10,000): consider a cheaper paid option later.

## Before the first sale

- [ ] Licence audit done; restricted components replaced or licensed; default model commercially licensed
- [ ] Lawyer drafted or reviewed: the licence and confidentiality agreement, the damages clause, limitation of liability, governing law and venue
- [ ] Fingerprinting built and tested
- [ ] E-signature flow and signatory records in place; business-only check
- [ ] Support scope, response targets and exclusions written down
- [ ] A company (not you personally) and insurance in place
- [ ] A contact route you are happy to publish (the README says: via the GitHub profile)
