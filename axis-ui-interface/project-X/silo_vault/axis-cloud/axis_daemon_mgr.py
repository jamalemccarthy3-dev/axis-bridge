#!/usr/bin/env python3
"""
axis_daemon_mgr.py
Production-grade daemon supervision manager for the AXIS sovereign infrastructure.
Delivers self-healing process recovery, continuous uptime tracking, and automated restarts.
"""

import subprocess
import sys
import time
import logging
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOGS_DIR / "axis_daemon_mgr.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AXIS-DAEMON-MGR] %(message)s"
)

class AxisDaemonSupervisor:
    def __init__(self):
        self.managed_scripts = {
            "cloud_server": BASE_DIR / "axis_cloud_server.py",
            "tunnel_bridge": BASE_DIR / "axis_tunnel_bridge.py",
            "router_bridge": BASE_DIR / "axis_router_bridge.py"
        }
        self.processes = {}
        self.restart_counts = {name: 0 for name in self.managed_scripts}
        self.start_times = {}

    def start_daemon(self, name):
        script_path = self.managed_scripts[name]
        if not script_path.exists():
            logging.error(f"Daemon script missing for '{name}' at {script_path}")
            print(f"[AXIS-DAEMON-MGR] [ERROR] Daemon script missing for '{name}' at {script_path}")
            return False
        
        print(f"[AXIS-DAEMON-MGR] Launching service: {name}...")
        logging.info(f"Launching service: {name}")
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.processes[name] = proc
            self.start_times[name] = time.time()
            return True
        except Exception as e:
            logging.error(f"Failed to start {name}: {e}")
            print(f"[AXIS-DAEMON-MGR] [ERROR] Failed to start {name}: {e}")
            return False

    def supervise_loop(self):
        print("[AXIS-DAEMON-MGR] Initializing self-healing supervision loop...")
        logging.info("Initializing self-healing supervision loop.")
        
        for name in self.managed_scripts:
            self.start_daemon(name)

        try:
            while True:
                time.sleep(3)
                for name in list(self.managed_scripts.keys()):
                    proc = self.processes.get(name)
                    if proc is None or proc.poll() is not None:
                        exit_code = proc.poll() if proc else "None"
                        uptime = time.time() - self.start_times.get(name, time.time()) if proc else 0
                        
                        msg = f"WARNING: Service '{name}' is down (Exit code: {exit_code}, Last uptime: {uptime:.2f}s)."
                        print(f"[AXIS-DAEMON-MGR] {msg}")
                        logging.warning(msg)
                        
                        self.restart_counts[name] += 1
                        print(f"[AXIS-DAEMON-MGR] Initiating self-healing recovery for '{name}' (Restart attempt #{self.restart_counts[name]})...")
                        logging.info(f"Initiating recovery for '{name}' (Attempt #{self.restart_counts[name]})")
                        
                        self.start_daemon(name)
        except KeyboardInterrupt:
            print("\n[AXIS-DAEMON-MGR] Shutdown signal received by operator. Terminating managed daemons...")
            logging.info("Shutdown signal received by operator.")
            self.shutdown_all()

    def shutdown_all(self):
        for name, proc in self.processes.items():
            if proc.poll() is None:
                print(f"  [STOPPING] Terminating daemon '{name}' (PID {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                logging.info(f"Terminated daemon '{name}'")
        self.processes.clear()
        print("[AXIS-DAEMON-MGR] All daemons stopped cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    supervisor = AxisDaemonSupervisor()
    supervisor.supervise_loop()