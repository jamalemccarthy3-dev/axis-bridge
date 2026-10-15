"""nexxus_link.py - this engine's ORCHESTRATOR door to NEXXUS over the orchestrator bus (ORCHESTRATOR_BUS.md in the NEXXUS root folder).

    from nexxus_link import client
    link = client()                      # signs with NEXXUS_GOVERNANCE_SECRET, talks to NEXXUS_MESH_URL (default http://127.0.0.1:8000)
    link.ack(order_id); link.built(order_id, artifact_path)
Only the orchestrator (governor) uses this. Silos never talk to NEXXUS directly.
"""
import os
import sys

ENGINE = "axis-SandM"
ORCHESTRATOR = "sandm.governor"


def _root():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        if os.path.isfile(os.path.join(d, "orchestrator_client.py")):
            return d
        d = os.path.dirname(d)
    raise ImportError("orchestrator_client.py not found above this engine (it lives in the NEXXUS root folder)")


def client(**kwargs):
    root = _root()
    if root not in sys.path:
        sys.path.append(root)                      # appended, so it can never shadow this engine's own lib/ or config/
    from orchestrator_client import OrchestratorClient
    return OrchestratorClient(ENGINE, ORCHESTRATOR, **kwargs)
