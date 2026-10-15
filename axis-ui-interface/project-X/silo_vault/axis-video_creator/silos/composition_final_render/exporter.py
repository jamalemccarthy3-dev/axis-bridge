from lib.exporter_tool import write_to_disk
from config.exporter_config import CONFIG


def run_exporter(source, name=None):
    """Copies the finished video to the configured export folder and verifies the copy. -> write_to_disk's result."""
    return write_to_disk(CONFIG["output_path"], source, name)
