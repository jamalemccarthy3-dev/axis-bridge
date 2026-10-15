import hashlib
import importlib
import json
import os
import pathlib
import pkgutil
import time


class Diagnostics_District:

  def __init__(self):
    self.signal_file = "bridge_signal.json"
    self.folders_to_check = ["Archives", "Final_Drafts", "Rough_Drafts"]
    print("Diagnostics District: Online. Running system health checks...")

  def get_file_hash(self, filepath):
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
      while chunk := f.read(8192):
        hasher.update(chunk)
    return hasher.hexdigest()

  def scan_active_engines(self, base_path: str = "engines") -> dict:
    """Dynamically probes the backend bridge to map active engine modules."""
    discovered = {}
    target_dir = pathlib.Path(base_path)

    if not target_dir.exists():
      return discovered

    for _, module_name, _ in pkgutil.iter_modules([str(target_dir)]):
      try:
        module = importlib.import_module(f"{base_path}.{module_name}")
        if hasattr(module, "register_engine"):
          discovered[module_name] = module.register_engine()
        elif hasattr(module, "Engine"):
          discovered[module_name] = module.Engine()
      except Exception as e:
        discovered[module_name] = {"status": "error", "details": str(e)}

    return discovered

  def run(self):
    while True:
      # Simple diagnostic: Scan folders for file updates
      for folder in self.folders_to_check:
        if os.path.exists(folder):
          files = os.listdir(folder)

      # Automatically discover active engines on every loop pass
      active_engines = self.scan_active_engines()

      # Write the live state to a shared JSON file for the front end / UI
      system_status = {
          "timestamp": time.time(),
          "access_gate": "active",
          "active_engines": list(active_engines.keys()),
          "engine_details": str(active_engines),
      }

      try:
        with open("bridge_status.json", "w") as status_file:
          json.dump(system_status, status_file, indent=4)
      except Exception as e:
        print(f"Diagnostics: Failed to write bridge status -> {e}")

      # Watch for a specific manual trigger command
      try:
        with open(self.signal_file, "r") as f:
          signal = json.load(f)
          command_val = signal.get("command", "")
          if isinstance(command_val, str) and "status" in command_val.lower():
            print("Diagnostics: Running full system audit...")
            print(
                f"Diagnostics: Discovered active engines ->"
                f" {list(active_engines.keys())}"
            )
      except Exception:
        pass

      time.sleep(10)  # Run diagnostics every 10 seconds


if __name__ == "__main__":
  district = Diagnostics_District()
  district.run()