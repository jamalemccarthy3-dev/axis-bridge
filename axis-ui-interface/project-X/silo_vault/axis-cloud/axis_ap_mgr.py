#!/usr/bin/env python3
"""
axis_ap_mgr.py
Production-grade final implementation. Manages local Wi-Fi Access Point (AP) 
creation, tethering, and wireless interface states across the AXIS infrastructure.
"""

import subprocess
import json
import sys

HOTSPOT_NAME = "AXIS-Sovereign-AP"

class AxisApMgr:
    def __init__(self, hotspot_name=HOTSPOT_NAME):
        self.hotspot_name = hotspot_name

    def start_ap(self, ssid=None, password=None):
        """Starts or brings up the local Wi-Fi Access Point using NetworkManager (nmcli)."""
        target_ssid = ssid or self.hotspot_name
        try:
            cmd_up = ["nmcli", "connection", "up", target_ssid]
            result = subprocess.run(cmd_up, capture_output=True, text=True)
            
            if result.returncode != 0:
                cmd_create = ["nmcli", "device", "wifi", "hotspot", "ifname", "wlan0", "ssid", target_ssid]
                if password:
                    cmd_create.extend(["password", password])
                result = subprocess.run(cmd_create, capture_output=True, text=True, check=True)
            
            print(f"[AXIS-AP-MGR] Access Point '{target_ssid}' successfully activated.")
            return {"success": True, "output": result.stdout.strip()}
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() or e.stdout.strip()
            print(f"[AXIS-AP-MGR] ERROR: Failed to start Access Point: {error_msg}")
            return {"success": False, "error": error_msg}

    def stop_ap(self, ssid=None):
        """Deactivates the local Wi-Fi Access Point."""
        target_ssid = ssid or self.hotspot_name
        try:
            cmd = ["nmcli", "connection", "down", target_ssid]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"[AXIS-AP-MGR] Access Point '{target_ssid}' successfully deactivated.")
            return {"success": True, "output": result.stdout.strip()}
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() or e.stdout.strip()
            print(f"[AXIS-AP-MGR] ERROR: Failed to stop Access Point: {error_msg}")
            return {"success": False, "error": error_msg}

    def status(self):
        """Queries wireless device status and active connection states."""
        try:
            cmd = ["nmcli", "device", "status"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return {"success": True, "output": result.stdout.strip()}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": e.stderr.strip()}

if __name__ == "__main__":
    manager = AxisApMgr()
    if len(sys.argv) > 1:
        action = sys.argv[1].lower()
        if action == "start":
            pwd = sys.argv[2] if len(sys.argv) > 2 else None
            print(json.dumps(manager.start_ap(password=pwd), indent=2))
        elif action == "stop":
            print(json.dumps(manager.stop_ap(), indent=2))
        else:
            print(json.dumps(manager.status(), indent=2))
    else:
        print(json.dumps(manager.status(), indent=2))