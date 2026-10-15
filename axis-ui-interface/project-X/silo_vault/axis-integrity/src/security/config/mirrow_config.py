# Mirror configuration for Access Integrity
ISOLATION_MODE = True
STORAGE_DESTINATION = "FUCHSIA_BOX"
RETENTION_POLICY = "STRICT"

def get_config():
    return {
        "isolation": ISOLATION_MODE,
        "destination": STORAGE_DESTINATION,
        "retention": RETENTION_POLICY
    }