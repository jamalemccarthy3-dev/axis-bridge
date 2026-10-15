class SearchRoutingConfig:
    def __init__(self):
        # The keys below map to full, absolute URLs with the required 'https://' scheme.
        self.endpoints = {
            "archive": "https://archive.org/wayback/available",
            "search": "https://www.google.com/search"
        }
        
        # This points to the key, not the path.
        self.default_route = "archive"