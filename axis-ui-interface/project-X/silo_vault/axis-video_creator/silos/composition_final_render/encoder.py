from lib.encoder_tool import compress_stream
from config.encoder_config import CONFIG


def run_encoder(frames_dir, output=None, fps=24, audio=None):
    """Encodes a folder of frames with the configured codec ('auto' falls back to gif when ffmpeg is missing). -> compress_stream's result."""
    return compress_stream(CONFIG["codec"], frames_dir, output, fps, CONFIG["bitrate"], audio)
