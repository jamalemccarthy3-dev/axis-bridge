# Imports
from src.relay import UniversalRelay
from src.orchestrator import orchestrator as Orchestrator
from src.security import SecureGatekeeper
from lib.bridge import UtilityBridge


def initialize_ai_environment():
    """Builds the four parts of the link. -> (relay, orchestrator, security, bridge)."""
    return UniversalRelay(), Orchestrator(), SecureGatekeeper(), UtilityBridge()


# Execution
if __name__ == "__main__":
    relay, orchestrator, security, bridge = initialize_ai_environment()
    print("Link parts created: relay at rest, orchestrator %s, bridge ready." % orchestrator.state)
