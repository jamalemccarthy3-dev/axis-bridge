# diagnostic_smoke_test_config.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VAULT_DIR = BASE_DIR / "asset_vault"
STAGING_DIR = BASE_DIR / "render_staging"

SERVER_ENDPOINT = "http://localhost:8000/api/vault/list"
TIMEOUT_SECONDS = 3
TARGET_EXTENSION = ".glb"