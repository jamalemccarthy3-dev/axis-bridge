import json
import time

# This district manages live economic and sports statistics
class Stats_District:
    def __init__(self):
        self.signal_file = "bridge_signal.json"
        print("Stats District: Online. Monitoring for Economic and Sports queries.")

    def run(self):
        last_command = ""
        while True:
            try:
                with open(self.signal_file, "r") as f:
                    signal = json.load(f)
                    cmd = signal['command'].lower()
                    
                    if cmd != last_command:
                        # Logic to handle specific data requests
                        if "stocks" in cmd or "market" in cmd:
                            print("Action: Fetching market statistics...")
                            # Logic here to fetch/display stock data
                        elif "sports" in cmd or "score" in cmd:
                            print("Action: Fetching sports statistics...")
                            # Logic here to fetch/display sports data
                        last_command = cmd
            except:
                pass
            time.sleep(1)

if __name__ == "__main__":
    district = Stats_District()
    district.run()
