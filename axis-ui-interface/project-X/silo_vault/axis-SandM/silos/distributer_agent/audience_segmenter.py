import sys
from lib.audience_segmenter_tool import SegmenterEngine
from config.audience_segmenter_config import AudienceSegmenterConfig

def run_audience_segmenter():
    """Main orchestrator for the Audience Segmenter agent."""
    config = AudienceSegmenterConfig()
    engine = SegmenterEngine(config)
    
    try:
        segments = engine.analyze_audience_data()
        print(f"Segmentation: {segments['status']}, {len(segments['segments'])} segment(s) from {segments['people']} people.")
    except Exception as e:
        print(f"Critical error in audience_segmenter: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_audience_segmenter()