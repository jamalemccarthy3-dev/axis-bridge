# diagnostic_smoke_test.py
import urllib.request
from src.config.diagnostic_smoke_test_config import VAULT_DIR, STAGING_DIR, SERVER_ENDPOINT, TIMEOUT_SECONDS, TARGET_EXTENSION

def execute_asset_check():
    results = {"filesystem_pass": False, "server_pass": False, "assets_found": []}
    
    # Filesystem check
    vault_exists = VAULT_DIR.exists()
    staging_exists = STAGING_DIR.exists()
    results["filesystem_pass"] = vault_exists and staging_exists
    
    glbs = list(VAULT_DIR.glob(f"*{TARGET_EXTENSION}")) + list(STAGING_DIR.glob(f"*{TARGET_EXTENSION}"))
    results["assets_found"] = [str(f.name) for f in glbs]

    # Server endpoint route check
    try:
        req = urllib.request.urlopen(SERVER_ENDPOINT, timeout=TIMEOUT_SECONDS)
        results["server_pass"] = (req.getcode() == 200)
    except Exception:
        results["server_pass"] = False

    return results