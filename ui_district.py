import tkinter as tk
import json
import time
import threading
import os

class UI_District:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AXIS UI - Island Command")
        self.root.geometry("500x500")
        self.root.configure(bg="#1a1a1a")
        
        self.status_label = tk.Label(self.root, text="STATUS: Ready", fg="#00ff00", bg="#1a1a1a")
        self.status_label.pack(pady=10)
        
        # Area to list your current working files
        self.file_list = tk.Listbox(self.root, bg="#000", fg="#00ff00", width=60)
        self.file_list.pack(pady=20)
        
        self.watcher = threading.Thread(target=self.watch_bridge, daemon=True)
        self.watcher.start()
        
        self.root.mainloop()

    def watch_bridge(self):
        last_command = ""
        while True:
            try:
                with open("bridge_signal.json", "r") as f:
                    signal = json.load(f)
                    cmd = signal['command']
                    if cmd != last_command:
                        self.status_label.config(text=f"AXIS COMMAND: {cmd}")
                        self.update_file_display(cmd)
                        last_command = cmd
            except:
                pass
            time.sleep(0.5)

    def update_file_display(self, command):
        # Logic: If you say 'show drafts', it scans your Rough_Drafts folder
        if "draft" in command.lower():
            self.file_list.delete(0, tk.END)
            files = os.listdir("Rough_Drafts")
            for f in files:
                self.file_list.insert(tk.END, f)

if __name__ == "__main__":
    UI_District()
