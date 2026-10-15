import sys
from pathlib import Path

# Explicit absolute path direct injection to the root floor of NEXXUS
nexxus_root = Path("../nexxus") # Updated relative path pointing directly to nexxus
if str(nexxus_root) not in sys.path:
    sys.path.insert(0, str(nexxus_root))

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from nexxus_spider import NexxusSpider
from config.web_crawling_config import WebCrawlingConfig

class WebCrawlingNexxus:
    """
    web_crawling_nexxus.py
    Bridge component linking the search engine
    framework with the remote web crawling infrastructure
    configuration.
    """

    def __init__(self):
        self.config = WebCrawlingConfig()

    def trigger_crawl(self, url):
        """
        Triggers the crawling sequence
        programmatically using Scrapy CrawlerProcess.
        """
        endpoint = self.config.api_endpoint

        # Initialize Scrapy process with default project settings
        process = CrawlerProcess(get_project_settings())

        # Pass the dynamic start_url argument to NexxusSpider
        process.crawl(NexxusSpider, start_url=url)

        # Start the crawling engine execution loop
        process.start()

        return f"Crawling executed for {url} via endpoint: {endpoint}"

# Initialize the nexxus bridge
crawler_nexxus = WebCrawlingNexxus()

if __name__ == "__main__":
    # Test execution when calling the script directly
    result = crawler_nexxus.trigger_crawl("https://example.com")
    print(result)