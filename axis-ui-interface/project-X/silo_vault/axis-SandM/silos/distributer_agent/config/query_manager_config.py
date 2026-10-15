class QueryManagerConfig:
    def __init__(self):
        # Operational parameters for the Query Manager
        self.QUEUE_LIMIT = 1000
        self.POLLING_RATE_MS = 500
        
        # Priority settings
        self.ENABLE_PRIORITY_ROUTING = True
        self.DEFAULT_TIMEOUT = 30 # seconds
