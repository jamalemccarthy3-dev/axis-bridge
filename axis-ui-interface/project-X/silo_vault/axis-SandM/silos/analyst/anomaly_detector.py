import sys
from lib.anomaly_detector_tool import AnomalyEngine
from config.anomaly_detector_config import AnomalyDetectorConfig

def run_anomaly_detector():
    """Main orchestrator for the Anomaly Detector agent."""
    config = AnomalyDetectorConfig()
    engine = AnomalyEngine(config)
    
    try:
        # Scanning for deviations from established baseline protocols
        report = engine.scan_for_irregularities()
        if not report['is_secure']:
            print(f"SECURITY ALERT: {report['threat_level']} detected.")
        else:
            print("System integrity verified: No anomalies detected.")
    except Exception as e:
        print(f"Critical error in anomaly_detector: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_anomaly_detector()