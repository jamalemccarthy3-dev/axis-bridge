# DELIVER: The Hand-off Brain
# Purpose: Coordinates the transmission and verifies receipt.
import deliverer_config as config
import deliverer_tool as tool


def send_package(packet, destination):
    """Sends the packet and confirms the hand-off. DELIVERED only when the tool sent it AND the read-back verified it (that verification is the receipt: with
    REQUIRE_DESTINATION_ACK a package whose receipt could not be verified is FAILED). -> {"status": "DELIVERED"|"FAILED", "ack": bool, ...the tool's record or reason}."""
    result = tool.transmit_packet(packet, destination)
    if result["status"] == "SENT" and (result.get("verified") or not config.REQUIRE_DESTINATION_ACK):
        return dict(result, status="DELIVERED", ack=bool(result.get("verified")))
    return dict(result, status="FAILED", ack=False)
