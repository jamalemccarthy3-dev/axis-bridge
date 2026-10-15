import json
import os

def run_factory_pipeline_test():
    print("--- Initiating Factory Pipeline Test ---")
    pulse_file = 'pipeline_pulse.json'
    
    if not os.path.exists(pulse_file):
        print("ERROR: pipeline_pulse.json not found on the floor.")
        return

    try:
        with open(pulse_file, 'r') as f:
            data = json.load(f)
            
        print("Pulse File Loaded Successfully.")
        print(f"Current Project: {data['pipeline_pulse']['active_project_id']}")
        print("Verifying Node Communications:")
        
        nodes = data['pipeline_pulse']['node_status']
        for node, status in nodes.items():
            print(f"- {node.capitalize()}: {status}")
            
        # Basic validation logic
        if all(status in ['CONNECTED', 'READY', 'LISTENING'] for status in nodes.values()):
            print("\nSUCCESS: All nodes are communicating. Factory Pipeline is OPEN.")
        else:
            print("\nWARNING: Pipeline integrity check flagged an issue in node status.")
            
    except Exception as e:
        print(f"ERROR: Could not parse pulse file: {e}")

if __name__ == "__main__":
    run_factory_pipeline_test()