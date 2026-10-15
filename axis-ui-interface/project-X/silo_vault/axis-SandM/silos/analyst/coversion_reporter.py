import sys
from lib.conversion_reporter_tool import ReporterEngine
from config.conversion_reporter_config import ConversionReporterConfig

def run_conversion_reporter():
    """Main orchestrator for the Conversion Reporter agent."""
    config = ConversionReporterConfig()
    engine = ReporterEngine(config)
    
    try:
        # Generating high-yield performance reports
        report = engine.generate_financial_summary()
        print(f"Reporting complete. Current ROI: {report['roi_percentage']}%")
    except Exception as e:
        print(f"Critical error in conversion_reporter: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_conversion_reporter()
