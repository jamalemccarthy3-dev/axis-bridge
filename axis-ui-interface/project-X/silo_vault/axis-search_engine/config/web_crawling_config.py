# web_crawling/web_crawling_config.py

class WebCrawlingConfig:
    """
    Configuration for web_crawling.
    Points to remote infrastructure for stretched operation.
    """
    def __init__(self):
        self.api_endpoint = "https://api.sovereign-shift.net/v1/crawl"
        self.timeout = 15.0
        self.concurrency = 20