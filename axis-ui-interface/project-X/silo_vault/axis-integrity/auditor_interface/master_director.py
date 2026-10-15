# MASTER_DIRECTOR: The Orchestrator Brain
# Purpose: Decides the mission flow and initiates command sequences.
import master_director_tool as tool

SEQUENCES = {"init": ["INIT_TASK", "VERIFY"], "snapshot": ["SNAPSHOT", "REPORT"], "pause": ["PAUSE"], "resume": ["RESUME"]}


def run_sequence(sequence_name, targets):
    """Sends each command of a named sequence (init, snapshot, pause, resume) to every target silo. -> {"sequence", "results": [dispatch result per command and target], "all_queued": bool}.
    An unknown sequence raises ValueError."""
    if sequence_name not in SEQUENCES:
        raise ValueError("unknown sequence %r (have %s)" % (sequence_name, sorted(SEQUENCES)))
    results = [dict(tool.dispatch_command(t, cmd), target=t) for t in targets for cmd in SEQUENCES[sequence_name]]
    return {"sequence": sequence_name, "results": results, "all_queued": bool(results) and all(r["queued"] for r in results)}
