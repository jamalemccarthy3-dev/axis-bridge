import requests
# Point directly to the 'config' folder
from config.web_crawling_config import WebCrawlingConfig

class WebCrawling:
    """Engine for remote web crawling operations."""
    def __init__(self):
        self.config = WebCrawlingConfig()

    def crawl(self, url):
        """Fetches data from remote source."""
        try:
            response = requests.post(
                self.config.api_endpoint,
                json={"url": url},
                timeout=self.config.timeout
            )
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": "remote_fetch_failed"}
        except Exception as e:
            return {"error": str(e)}