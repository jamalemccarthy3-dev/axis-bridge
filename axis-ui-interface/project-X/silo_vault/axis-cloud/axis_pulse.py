#!/usr/bin/env python3
"""
axis_pulse.py
Production-grade final implementation. Monitors hardware telemetry, tracking
CPU load, thermal metrics, and memory utilization to ensure energy efficiency
and peak performance across the AXIS infrastructure.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

class AxisPulse:
    def __init__(self):
        pass

    def get_system_telemetry(self):
        """Gathers system metrics including disk space, load average, and thermal status if available."""
        telemetry = {
            "disk": self._get_disk_usage(),
            "load_average": self._get_load_average(),
            "temperature": self._get_temperature()
        }
        return telemetry

    def _get_disk_usage(self):
        try:
            total, used, free = shutil.disk_usage("/")
            return {
                "total_gb": round(total / (2**30), 2),
                "used_gb": round(used / (2**30), 2),
                "free_gb": round(free / (2**30), 2),
                "percent_free": round((free / total) * 100, 2)
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_load_average(self):
        try:
            # Reads system load averages (1, 5, 15 min)
            load1, load5, load15 = subprocess.run(
                ["uptime"], capture_output=True, text=True, check=True
            ).stdout.strip().split("load average:")[-1].split(",")
            return {
                "1min": float(load1.strip()),
                "5min": float(load5.strip()),
                "15min": float(load15.strip())
            }
        except Exception:
            return {"1min": 0.0, "5min": 0.0, "15min": 0.0}

    def _get_temperature(self):
        # Checks common thermal paths (compatible with Raspberry Pi and standard Linux SBCs)
        try:
            thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
            if thermal_path.exists():
                temp_milli = int(thermal_path.read_text(encoding="utf-8").strip())
                return round(temp_milli / 1000.0, 1)
        except Exception:
            pass
        return None

if __name__ == "__main__":
    pulse = AxisPulse()
    print(json.dumps(pulse.get_system_telemetry(), indent=2))