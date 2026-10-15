# archival_access/archival_access_config.py

class ArchivalAccessConfig:
    """
    Stretched configuration for archival_access.
    Defines remote archive service endpoints and access keys.
    """
    def __init__(self):
        self.archive_api_url = "https://archive.sovereign-shift.net/api/v1"
        self.storage_bucket = "sovereign-shift-archives"
        self.timeout = 30.0