from lib.source_manager import load_module
from config.src_manifest import CONFIG


def run_loader(module_path):
    """Loads a source file under the manifest's root, honouring the allowed extensions and pinned hashes. -> load_module's result."""
    return load_module(module_path, CONFIG["root_directory"], CONFIG["cache_enabled"], tuple(CONFIG["allowed_extensions"]), CONFIG["hashes"])
