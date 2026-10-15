import os

def run_discovery_test():
    print("--- Initiating Silo Discovery Test ---")
    
    # Using the same logic as your deployment tool to verify targets
    # Only folders with the 'ENABLE_DISCOVERY.txt' tag are included
    discovered_silos = [
        d for d in os.listdir('.') 
        if os.path.isdir(d) and os.path.exists(os.path.join(d, 'ENABLE_DISCOVERY.txt'))
    ]
    
    if not discovered_silos:
        print("Test Result: No tagged silos detected.")
    else:
        print(f"Test Result: Successfully detected {len(discovered_silos)} silos:")
        for silo in discovered_silos:
            print(f" -> Found Active Silo: {silo}")
            
    print("--- Discovery Test Complete ---")

if __name__ == "__main__":
    run_discovery_test()