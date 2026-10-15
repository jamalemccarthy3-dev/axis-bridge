from lib.temporal_tool import align_timeline
from config.temporal_config import CONFIG


def run_temporal(beats=None, audio_seconds=None):
    """Aligns beats (and optionally an audio length) to the configured frame rate; strict_sync follows sync_mode. -> align_timeline's result."""
    return align_timeline(CONFIG["frame_rate"], beats, audio_seconds, CONFIG["sync_mode"] == "strict")
