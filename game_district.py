import json
import time
import os

class Game_District:
    def __init__(self):
        self.signal_file = "bridge_signal.json"
        print("3D Game District: READY for asset initialization.")

    def run(self):
        last_command = ""
        while True:
            try:
                with open(self.signal_file, "r") as f:
                    signal = json.load(f)
                    cmd = signal['command'].lower()
                    
                    if cmd != last_command:
                        # Direct triggers for your specific Club assets
                        if "cage" in cmd:
                            print("Action: Loading Cage/Ring Asset...")
                        elif "car" in cmd:
                            print("Action: Loading Vehicle Asset...")
                        elif "betting" in cmd:
                            print("Action: Initializing Betting Logic...")
                        last_command = cmd
            except:
                pass
            time.sleep(0.5)

if __name__ == "__main__":
    district = Game_District()
    district.run()


