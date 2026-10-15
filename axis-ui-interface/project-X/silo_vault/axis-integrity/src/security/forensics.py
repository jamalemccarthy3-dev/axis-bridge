# FORENSICS: The Evidence Hand-off Brain
# Purpose: Orchestrates the hand-off to the Auditor.
import forensic_dump  # The Auditor's receiving bay
import forensics_tool as tool


def execute_forensic_handoff(silo_id, event_data):
    """Packages the evidence and hands it to the Auditor's dump. -> {"evidence_id", "path", "sha256"} (the dump's record)."""
    evidence = tool.collect_evidence(silo_id, event_data)
    path = forensic_dump.save_evidence(evidence)
    return {"evidence_id": evidence["evidence_id"], "path": path, "sha256": evidence["sha256"]}
