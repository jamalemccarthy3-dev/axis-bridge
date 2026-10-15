# storyboard_timing_precision_engine/utility/timing_engine.py
from lib.rhythm_calc import calculate_beat_alignment
from config.timing_config import CONFIG

def process_timing(blueprint):
    """-> the frame alignment of the blueprint's beats at the configured fps, or None if they cannot be put on whole frames (problems are printed)."""
    rhythm_data = calculate_beat_alignment(blueprint["beats"], CONFIG["fps"])
    if rhythm_data["is_synced"]:
        return rhythm_data
    print("[Timing Engine] Rhythm mismatch: %s" % "; ".join(rhythm_data["problems"] or ["boundary error over half a frame"]))
    return None

