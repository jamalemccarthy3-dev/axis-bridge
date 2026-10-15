class DataAggregatorConfig:
    def __init__(self):
        # Operational parameters for the Data Aggregator
        self.AGGREGATION_WINDOW_MIN = 15
        self.DATA_RETENTION_DAYS = 90
        
        # Integration parameters
        self.ENFORCE_DATA_NORMALIZATION = True
        self.SECURE_STORAGE_PATH = "/data/archives/silo_telemetry/"
