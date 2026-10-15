class TrendHarvesterConfig:
    def __init__(self):
        # Operational parameters for the Trend Harvester
        self.MONITOR_SOURCES = ["social_media_streams", "search_engine_api"]
        self.UPDATE_INTERVAL_SECONDS = 300
        
        # Filtering parameters
        self.MIN_VIRALITY_SCORE = 0.8
        self.AUTO_ADJUST_DISPATCH = True
