import ast
import json
import os
import subprocess
import time


class EmergencyHalt:
    """The emergency stop for what this engine itself started. Subprocesses are registered with register_process(); execute_halt() terminates THOSE (politely first, then by force after
    `grace` seconds) and writes a halt record, so nothing is killed that this engine does not own. With `terminate_all_subprocesses` off in the config it does a partial halt instead: it
    marks the failed node isolated (node= argument) and leaves the other processes running. config_path is a JSON or Python-dict-literal file."""

    def __init__(self, config_path, halt_file=None, grace=2.0):
        with open(config_path, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            self.config = json.loads(text)
        except ValueError:
            self.config = ast.literal_eval(text.strip())
        self.halt_file = halt_file or os.path.join(os.path.dirname(os.path.abspath(config_path)), "..", "..", "logs", "halt.json")
        self.grace = grace
        self._procs = []
        self.isolated = set()

    def register_process(self, proc):
        """Puts a subprocess.Popen under this halt's control. -> the process."""
        self._procs.append(proc)
        return proc

    def _record(self, reason, status, detail):
        os.makedirs(os.path.dirname(self.halt_file), exist_ok=True)
        with open(self.halt_file, "w", encoding="utf-8") as f:
            json.dump({"at": time.time(), "reason": str(reason), "status": status, **detail}, f)

    def execute_halt(self, reason, node=None):
        """-> {"status": "halted", "action": "shutdown_all_processes", "terminated": [pids], "killed": [pids], "already_stopped": [pids]} for a full halt, or
        {"status": "partial_halt", "action": "isolate_failed_node", "isolated": node} for a partial one (a node name is needed: ValueError without it)."""
        if self.config.get("terminate_all_subprocesses", True):
            terminated, killed, stopped = [], [], []
            for p in self._procs:
                if p.poll() is not None:
                    stopped.append(p.pid)
                    continue
                p.terminate()
                try:
                    p.wait(timeout=self.grace)
                    terminated.append(p.pid)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=self.grace)
                    killed.append(p.pid)
            self._procs.clear()
            out = {"status": "halted", "action": "shutdown_all_processes", "terminated": terminated, "killed": killed, "already_stopped": stopped}
        else:
            if not node:
                raise ValueError("a partial halt needs the name of the node to isolate")
            self.isolated.add(node)
            out = {"status": "partial_halt", "action": "isolate_failed_node", "isolated": node}
        self._record(reason, out["status"], {k: v for k, v in out.items() if k != "status"})
        return out
