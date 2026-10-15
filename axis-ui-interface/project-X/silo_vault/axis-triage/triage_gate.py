from lib.triage_gate_tool import load_triage_config, load_grid_map, clean_input, validate_route


class TriageGate:
    def __init__(self):
        # Initialize Triage settings and sync with the Master Grid
        self.config = load_triage_config()
        self.grid_map = load_grid_map()
        print("[TriageGate] Initialized. Linked to master grid mapping.")

    def run(self, raw_data, target_node):
        # 1. Sanitize the payload
        safe_data = clean_input(raw_data, self.config["blocked_patterns"])

        # 2. Validate route dynamically against config_map.json
        if validate_route(target_node, self.grid_map):
            print(f"[TriageGate] Success: Data routed to {target_node}.")
            return safe_data
        else:
            print(f"[TriageGate] Error: {target_node} does not exist in master grid.")
            return None


if __name__ == "__main__":
    gate = TriageGate()
    print(gate.run("select 1; drop table users", "axis-llm"))
