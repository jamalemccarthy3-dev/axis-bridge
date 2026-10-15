class CompetitorInsightScannerConfig:
    def __init__(self):
        # Operational parameters for the Competitor Insight Scanner
        self.MONITOR_CHANNELS = ["logistics_industry_feeds", "tech_security_journals"]
        self.SCAN_FREQUENCY_HOURS = 24
        
        # Intelligence filtering
        self.RELEVANCE_THRESHOLD = 0.75
        self.AUTO_ALERT_HIGH_THREAT = True
