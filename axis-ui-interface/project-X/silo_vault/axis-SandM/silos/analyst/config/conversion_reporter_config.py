class ConversionReporterConfig:
    def __init__(self):
        # Operational parameters for the Conversion Reporter
        self.REPORTING_FREQUENCY = "daily"
        self.CURRENCY = "USD"
        
        # Financial thresholds
        self.PROFIT_GOAL_THRESHOLD = 5000.00
        self.ENABLE_AUTO_EXPORT_PDF = True
