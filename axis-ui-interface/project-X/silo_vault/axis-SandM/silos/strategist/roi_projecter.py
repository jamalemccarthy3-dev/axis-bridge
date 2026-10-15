import sys
from lib.roi_projecter_tool import ROIProjecterEngine
from config.roi_projecter_config import ROIProjecterConfig

def run_roi_projection():
    """Main orchestrator for the ROI Projecter agent."""
    config = ROIProjecterConfig()
    engine = ROIProjecterEngine(config)
    
    try:
        projection = engine.calculate_projected_roi()
        print(f"ROI projection {projection['status']}. Expected yield: {projection['yield_pct']}%")
    except Exception as e:
        print(f"Critical error in roi_projecter: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_roi_projection()