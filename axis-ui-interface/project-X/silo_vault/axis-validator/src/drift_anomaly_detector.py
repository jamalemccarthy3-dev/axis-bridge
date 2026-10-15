"""
Core entry point for the drift_anomaly_detector module.
Binds configuration specs with underlying anomaly detector tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.drift_anomaly_detector_config import DRIFT_ANOMALY_CONFIG
from lib.drift_anomaly_detector_tool import DriftAnomalyDetectorTool

class DriftAnomalyDetector:
    def __init__(self):
        self.config = DRIFT_ANOMALY_CONFIG
        self.tool = DriftAnomalyDetectorTool(self.config)

    def detect(self, z_score: float) -> bool:
        """Executes the drift anomaly detection evaluation check."""
        normal, telemetry = self.tool.evaluate_anomaly(z_score)
        print(f"[{self.config['module_name']}] Anomaly Status -> Normal: {normal}")
        print(f"Telemetry Data: {telemetry}")
        return normal

if __name__ == "__main__":
    detector = DriftAnomalyDetector()
    # Sanity verification mock
    detector.detect(1.2)