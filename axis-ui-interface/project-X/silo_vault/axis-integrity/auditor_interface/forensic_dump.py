# FORENSIC_DUMP: The Logic
import forensic_dump_tool as tool


def run_dump(logs):
    """Writes the logs/evidence as one hash-chained dump file. -> its path."""
    return tool.execute_dump(logs, "audit_dump_snapshot")


def save_evidence(evidence):
    """The name src/security/forensics.py calls: hand the evidence to the dump."""
    return run_dump(evidence)
