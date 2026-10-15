import requests
# Point directly to the 'config' folder in the root
from config.archival_access_config import ArchivalAccessConfig

class ArchivalAccess:
    """Engine for fetching and interacting with remote archival data."""
    def __init__(self):
        self.config = ArchivalAccessConfig()

    def get_document(self, doc_id):
        """Retrieves a document from the remote archive service."""
        try:
            url = f"{self.config.archive_api_url}/fetch/{doc_id}"
            response = requests.get(url, timeout=self.config.timeout)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": "retrieval_failed"}
        except Exception as e:
            return {"error": str(e)}