# Final Copy: The Relay Configuration
class RelayConfig:
    def get_routing_rules(self):
        """Defines the routing table and node permissions."""
        return {
            "routing_table": "ACTIVE",
            "priority": "HIGH",
            "allow_cross_silo": False
        }
